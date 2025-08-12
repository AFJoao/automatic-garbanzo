"""
Sistema de upload via CDN ImageKit para veículos
Substitui o sistema de upload local por CDN
"""
import os
import uuid
import requests
import base64
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
from PIL import Image
import magic
import io
from src.models.vehicle import Vehicle, VehicleImage
from src.models.user import db
from src.routes.auth import require_admin

cdn_uploads_bp = Blueprint('cdn_uploads', __name__)

# Configurações do ImageKit
IMAGEKIT_PRIVATE_KEY = os.environ.get('IMAGEKIT_PRIVATE_KEY', '')
IMAGEKIT_PUBLIC_KEY = os.environ.get('IMAGEKIT_PUBLIC_KEY', '')
IMAGEKIT_URL_ENDPOINT = os.environ.get('IMAGEKIT_URL_ENDPOINT', '')

# Configurações de upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

def allowed_file(filename):
    """Verifica se o arquivo tem extensão permitida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_image_content(file_content):
    """Valida se o conteúdo é realmente uma imagem"""
    try:
        # Verificar MIME type
        mime = magic.Magic(mime=True)
        file_mime = mime.from_buffer(file_content)
        
        if not file_mime.startswith('image/'):
            return False
        
        # Tentar abrir com PIL
        with Image.open(io.BytesIO(file_content)) as img:
            img.verify()
        
        return True
    except Exception:
        return False

def generate_unique_filename(original_filename, vehicle_id):
    """Gera um nome único para o arquivo no CDN"""
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
    unique_id = str(uuid.uuid4())
    return f"vehicles/{vehicle_id}/{unique_id}.{ext}"

def upload_to_imagekit(file_content, filename, folder_path):
    """
    Faz upload de uma imagem para o ImageKit
    
    Args:
        file_content: Conteúdo binário do arquivo
        filename: Nome do arquivo
        folder_path: Caminho da pasta no ImageKit
    
    Returns:
        dict: Resposta do ImageKit ou None em caso de erro
    """
    try:
        # Converter conteúdo para base64
        file_base64 = base64.b64encode(file_content).decode('utf-8')
        
        # Preparar dados para upload
        upload_data = {
            'file': file_base64,
            'fileName': filename,
            'folder': folder_path,
            'useUniqueFileName': False,  # Já geramos nome único
            'tags': ['vehicle', 'concessionaria'],
            'isPrivateFile': False,
            'customCoordinates': '',
            'responseFields': 'fileId,name,size,filePath,url,fileType,height,width,thumbnailUrl'
        }
        
        # Headers para autenticação
        headers = {
            'Authorization': f'Basic {base64.b64encode(f"{IMAGEKIT_PRIVATE_KEY}:".encode()).decode()}'
        }
        
        # Fazer upload
        response = requests.post(
            'https://upload.imagekit.io/api/v1/files/upload',
            data=upload_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Erro no upload ImageKit: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Erro ao fazer upload para ImageKit: {e}")
        return None

def delete_from_imagekit(file_id):
    """
    Remove uma imagem do ImageKit
    
    Args:
        file_id: ID do arquivo no ImageKit
    
    Returns:
        bool: True se removido com sucesso, False caso contrário
    """
    try:
        # Headers para autenticação
        headers = {
            'Authorization': f'Basic {base64.b64encode(f"{IMAGEKIT_PRIVATE_KEY}:".encode()).decode()}'
        }
        
        # Fazer delete
        response = requests.delete(
            f'https://api.imagekit.io/v1/files/{file_id}',
            headers=headers,
            timeout=30
        )
        
        return response.status_code == 204
        
    except Exception as e:
        print(f"Erro ao deletar do ImageKit: {e}")
        return False

@cdn_uploads_bp.route('/cdn-upload', methods=['POST'])
@require_admin()
def cdn_upload_file():
    """
    Upload de imagem para um veículo via CDN ImageKit
    Requer autenticação de administrador
    """
    try:
        # Verificar configuração do ImageKit
        if not all([IMAGEKIT_PRIVATE_KEY, IMAGEKIT_PUBLIC_KEY, IMAGEKIT_URL_ENDPOINT]):
            return jsonify({'error': 'CDN não configurado. Verifique as variáveis de ambiente.'}), 500
        
        # Verificar se há arquivo na requisição
        if 'file' not in request.files:
            return jsonify({'error': 'Nenhum arquivo enviado'}), 400
        
        file = request.files['file']
        vehicle_id = request.form.get('vehicle_id')
        
        if file.filename == '':
            return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
        
        if not vehicle_id:
            return jsonify({'error': 'ID do veículo é obrigatório'}), 400
        
        # Verificar se o veículo existe
        vehicle = Vehicle.query.get(vehicle_id)
        if not vehicle:
            return jsonify({'error': 'Veículo não encontrado'}), 404
        
        # Verificar extensão do arquivo
        if not allowed_file(file.filename):
            return jsonify({'error': 'Tipo de arquivo não permitido'}), 400
        
        # Ler conteúdo do arquivo
        file_content = file.read()
        
        # Verificar tamanho do arquivo
        if len(file_content) > MAX_FILE_SIZE:
            return jsonify({'error': 'Arquivo muito grande (máximo 5MB)'}), 400
        
        # Validar se é realmente uma imagem
        if not validate_image_content(file_content):
            return jsonify({'error': 'Arquivo não é uma imagem válida'}), 400
        
        # Gerar nome único para o arquivo
        filename = generate_unique_filename(file.filename, vehicle_id)
        folder_path = f"/vehicles/{vehicle_id}"
        
        # Fazer upload para ImageKit
        upload_result = upload_to_imagekit(file_content, filename, folder_path)
        
        if not upload_result:
            return jsonify({'error': 'Erro ao fazer upload para CDN'}), 500
        
        # Salvar metadados no banco
        vehicle_image = VehicleImage(
            vehicle_id=vehicle_id,
            filename=upload_result['name'],
            original_filename=secure_filename(file.filename),
            file_path=upload_result['filePath'],
            file_size=upload_result['size'],
            mime_type=upload_result.get('fileType', file.content_type),
            image_order=len(vehicle.vehicle_images),
            cdn_file_id=upload_result['fileId'],  # Novo campo para ID do CDN
            cdn_url=upload_result['url']  # Novo campo para URL do CDN
        )
        
        db.session.add(vehicle_image)
        
        # Adicionar URL da imagem à lista do veículo
        vehicle.add_imagem(upload_result['url'])
        
        db.session.commit()
        
        return jsonify({
            'message': 'Imagem enviada com sucesso para CDN',
            'image': vehicle_image.to_dict(),
            'cdn_data': {
                'file_id': upload_result['fileId'],
                'url': upload_result['url'],
                'thumbnail_url': upload_result.get('thumbnailUrl'),
                'width': upload_result.get('width'),
                'height': upload_result.get('height')
            }
        }), 201
        
    except Exception as e:
        print(f"Erro no upload CDN: {e}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@cdn_uploads_bp.route('/cdn-uploads/<int:image_id>', methods=['DELETE'])
@require_admin()
def delete_cdn_image(image_id):
    """
    Remove uma imagem do CDN e do banco de dados
    Requer autenticação de administrador
    """
    try:
        image = VehicleImage.query.get(image_id)
        if not image:
            return jsonify({'error': 'Imagem não encontrada'}), 404
        
        # Remover do ImageKit se tiver file_id
        if hasattr(image, 'cdn_file_id') and image.cdn_file_id:
            delete_success = delete_from_imagekit(image.cdn_file_id)
            if not delete_success:
                print(f"Aviso: Não foi possível remover imagem {image.cdn_file_id} do ImageKit")
        
        # Remover da lista do veículo
        vehicle = Vehicle.query.get(image.vehicle_id)
        if vehicle and hasattr(image, 'cdn_url') and image.cdn_url:
            vehicle.remove_imagem(image.cdn_url)
        
        # Remover do banco
        db.session.delete(image)
        db.session.commit()
        
        return jsonify({'message': 'Imagem removida com sucesso do CDN e banco de dados'}), 200
        
    except Exception as e:
        print(f"Erro ao deletar imagem CDN: {e}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@cdn_uploads_bp.route('/cdn-uploads/<int:vehicle_id>/images', methods=['GET'])
def get_vehicle_cdn_images(vehicle_id):
    """
    Lista todas as imagens de um veículo do CDN
    Endpoint público
    """
    try:
        vehicle = Vehicle.query.get(vehicle_id)
        if not vehicle:
            return jsonify({'error': 'Veículo não encontrado'}), 404
        
        images = VehicleImage.query.filter_by(vehicle_id=vehicle_id).order_by(VehicleImage.image_order).all()
        
        # Gerar URLs de transformação do ImageKit para diferentes tamanhos
        images_data = []
        for image in images:
            image_dict = image.to_dict()
            
            # Se tiver URL do CDN, gerar variações
            if hasattr(image, 'cdn_url') and image.cdn_url:
                base_url = image.cdn_url
                image_dict['urls'] = {
                    'original': base_url,
                    'large': f"{base_url}?tr=w-1200,h-800,c-maintain_ratio",
                    'medium': f"{base_url}?tr=w-800,h-600,c-maintain_ratio", 
                    'thumbnail': f"{base_url}?tr=w-300,h-200,c-maintain_ratio",
                    'webp_medium': f"{base_url}?tr=w-800,h-600,c-maintain_ratio,f-webp",
                    'webp_thumbnail': f"{base_url}?tr=w-300,h-200,c-maintain_ratio,f-webp"
                }
            
            images_data.append(image_dict)
        
        return jsonify({
            'images': images_data,
            'cdn_endpoint': IMAGEKIT_URL_ENDPOINT
        }), 200
        
    except Exception as e:
        print(f"Erro ao listar imagens CDN: {e}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@cdn_uploads_bp.route('/cdn-uploads/bulk', methods=['POST'])
@require_admin()
def bulk_cdn_upload():
    """
    Upload múltiplo de imagens para um veículo via CDN
    Requer autenticação de administrador
    """
    try:
        # Verificar configuração do ImageKit
        if not all([IMAGEKIT_PRIVATE_KEY, IMAGEKIT_PUBLIC_KEY, IMAGEKIT_URL_ENDPOINT]):
            return jsonify({'error': 'CDN não configurado. Verifique as variáveis de ambiente.'}), 500
        
        vehicle_id = request.form.get('vehicle_id')
        
        if not vehicle_id:
            return jsonify({'error': 'ID do veículo é obrigatório'}), 400
        
        # Verificar se o veículo existe
        vehicle = Vehicle.query.get(vehicle_id)
        if not vehicle:
            return jsonify({'error': 'Veículo não encontrado'}), 404
        
        files = request.files.getlist('files')
        
        if not files:
            return jsonify({'error': 'Nenhum arquivo enviado'}), 400
        
        uploaded_images = []
        errors = []
        
        for file in files:
            try:
                if file.filename == '':
                    continue
                
                if not allowed_file(file.filename):
                    errors.append(f'{file.filename}: Tipo de arquivo não permitido')
                    continue
                
                # Ler conteúdo
                file_content = file.read()
                
                # Verificar tamanho
                if len(file_content) > MAX_FILE_SIZE:
                    errors.append(f'{file.filename}: Arquivo muito grande')
                    continue
                
                # Validar imagem
                if not validate_image_content(file_content):
                    errors.append(f'{file.filename}: Não é uma imagem válida')
                    continue
                
                # Gerar nome único
                filename = generate_unique_filename(file.filename, vehicle_id)
                folder_path = f"/vehicles/{vehicle_id}"
                
                # Upload para ImageKit
                upload_result = upload_to_imagekit(file_content, filename, folder_path)
                
                if not upload_result:
                    errors.append(f'{file.filename}: Erro no upload para CDN')
                    continue
                
                # Salvar no banco
                vehicle_image = VehicleImage(
                    vehicle_id=vehicle_id,
                    filename=upload_result['name'],
                    original_filename=secure_filename(file.filename),
                    file_path=upload_result['filePath'],
                    file_size=upload_result['size'],
                    mime_type=upload_result.get('fileType', file.content_type),
                    image_order=len(vehicle.vehicle_images) + len(uploaded_images),
                    cdn_file_id=upload_result['fileId'],
                    cdn_url=upload_result['url']
                )
                
                db.session.add(vehicle_image)
                vehicle.add_imagem(upload_result['url'])
                
                uploaded_images.append({
                    'image': vehicle_image.to_dict(),
                    'cdn_data': upload_result
                })
                
            except Exception as e:
                errors.append(f'{file.filename}: Erro ao processar - {str(e)}')
        
        db.session.commit()
        
        return jsonify({
            'message': f'{len(uploaded_images)} imagens enviadas com sucesso para CDN',
            'uploaded_images': uploaded_images,
            'errors': errors
        }), 201 if uploaded_images else 400
        
    except Exception as e:
        print(f"Erro no upload bulk CDN: {e}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@cdn_uploads_bp.route('/cdn-config', methods=['GET'])
def get_cdn_config():
    """
    Retorna configuração pública do CDN para o frontend
    """
    return jsonify({
        'imagekit_url_endpoint': IMAGEKIT_URL_ENDPOINT,
        'imagekit_public_key': IMAGEKIT_PUBLIC_KEY,
        'max_file_size': MAX_FILE_SIZE,
        'allowed_extensions': list(ALLOWED_EXTENSIONS)
    }), 200

