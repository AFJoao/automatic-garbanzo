"""
Sistema de upload e gerenciamento de imagens para veículos
"""
import os
import uuid
from flask import Blueprint, request, jsonify, send_from_directory, current_app
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
from PIL import Image
import magic
from src.models.vehicle import Vehicle, VehicleImage
from src.models.user import db
from src.routes.auth import require_admin

uploads_bp = Blueprint('uploads', __name__)

# Configurações de upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
IMAGE_SIZES = {
    'thumbnail': (300, 200),
    'medium': (800, 600),
    'large': (1200, 800)
}

def allowed_file(filename):
    """Verifica se o arquivo tem extensão permitida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_image(file_path):
    """Valida se o arquivo é realmente uma imagem"""
    try:
        # Verificar MIME type
        mime = magic.Magic(mime=True)
        file_mime = mime.from_file(file_path)
        
        if not file_mime.startswith('image/'):
            return False
        
        # Tentar abrir com PIL
        with Image.open(file_path) as img:
            img.verify()
        
        return True
    except Exception:
        return False

def generate_unique_filename(original_filename):
    """Gera um nome único para o arquivo"""
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    unique_id = str(uuid.uuid4())
    return f"{unique_id}.{ext}" if ext else unique_id

def create_upload_directory():
    """Cria o diretório de uploads se não existir"""
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir

def resize_image(image_path, output_path, size):
    """Redimensiona uma imagem mantendo a proporção"""
    try:
        with Image.open(image_path) as img:
            # Converter para RGB se necessário
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Redimensionar mantendo proporção
            img.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Salvar com qualidade otimizada
            img.save(output_path, 'JPEG', quality=85, optimize=True)
        
        return True
    except Exception as e:
        print(f"Erro ao redimensionar imagem: {e}")
        return False

@uploads_bp.route('/upload', methods=['POST'])
@require_admin()
def upload_file():
    """
    Upload de imagem para um veículo
    Requer autenticação de administrador
    """
    try:
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
        
        # Verificar tamanho do arquivo
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': 'Arquivo muito grande (máximo 5MB)'}), 400
        
        # Criar diretório de uploads
        upload_dir = create_upload_directory()
        
        # Gerar nome único para o arquivo
        filename = generate_unique_filename(file.filename)
        file_path = os.path.join(upload_dir, filename)
        
        # Salvar arquivo temporariamente
        file.save(file_path)
        
        # Validar se é realmente uma imagem
        if not validate_image(file_path):
            os.remove(file_path)
            return jsonify({'error': 'Arquivo não é uma imagem válida'}), 400
        
        # Criar versões redimensionadas
        versions_created = []
        try:
            # Versão original otimizada
            original_path = os.path.join(upload_dir, f"original_{filename}")
            if resize_image(file_path, original_path, (1920, 1080)):
                versions_created.append(original_path)
            
            # Versão média
            medium_path = os.path.join(upload_dir, f"medium_{filename}")
            if resize_image(file_path, medium_path, IMAGE_SIZES['medium']):
                versions_created.append(medium_path)
            
            # Versão thumbnail
            thumb_path = os.path.join(upload_dir, f"thumb_{filename}")
            if resize_image(file_path, thumb_path, IMAGE_SIZES['thumbnail']):
                versions_created.append(thumb_path)
            
        except Exception as e:
            # Limpar arquivos criados em caso de erro
            for version_path in versions_created:
                if os.path.exists(version_path):
                    os.remove(version_path)
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({'error': 'Erro ao processar imagem'}), 500
        
        # Remover arquivo temporário original
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Salvar metadados no banco
        vehicle_image = VehicleImage(
            vehicle_id=vehicle_id,
            filename=filename,
            original_filename=secure_filename(file.filename),
            file_path=f"uploads/{filename}",
            file_size=file_size,
            mime_type=file.content_type,
            image_order=len(vehicle.vehicle_images)
        )
        
        db.session.add(vehicle_image)
        
        # Adicionar imagem à lista do veículo
        vehicle.add_imagem(filename)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Imagem enviada com sucesso',
            'image': vehicle_image.to_dict(),
            'urls': {
                'original': f'/api/uploads/original_{filename}',
                'medium': f'/api/uploads/medium_{filename}',
                'thumbnail': f'/api/uploads/thumb_{filename}'
            }
        }), 201
        
    except Exception as e:
        return jsonify({'error': 'Erro interno do servidor'}), 500

@uploads_bp.route('/uploads/<filename>')
def uploaded_file(filename):
    """
    Serve arquivos de upload
    Endpoint público para visualização de imagens
    """
    try:
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
        return send_from_directory(upload_dir, filename)
    except Exception as e:
        return jsonify({'error': 'Arquivo não encontrado'}), 404

@uploads_bp.route('/uploads/<int:vehicle_id>/images', methods=['GET'])
def get_vehicle_images(vehicle_id):
    """
    Lista todas as imagens de um veículo
    Endpoint público
    """
    try:
        vehicle = Vehicle.query.get(vehicle_id)
        if not vehicle:
            return jsonify({'error': 'Veículo não encontrado'}), 404
        
        images = VehicleImage.query.filter_by(vehicle_id=vehicle_id).order_by(VehicleImage.image_order).all()
        
        return jsonify({
            'images': [image.to_dict() for image in images]
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Erro interno do servidor'}), 500

@uploads_bp.route('/uploads/<int:image_id>', methods=['DELETE'])
@require_admin()
def delete_image(image_id):
    """
    Remove uma imagem
    Requer autenticação de administrador
    """
    try:
        image = VehicleImage.query.get(image_id)
        if not image:
            return jsonify({'error': 'Imagem não encontrada'}), 404
        
        # Remover arquivos físicos
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
        files_to_remove = [
            os.path.join(upload_dir, image.filename),
            os.path.join(upload_dir, f"original_{image.filename}"),
            os.path.join(upload_dir, f"medium_{image.filename}"),
            os.path.join(upload_dir, f"thumb_{image.filename}")
        ]
        
        for file_path in files_to_remove:
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Remover da lista do veículo
        vehicle = Vehicle.query.get(image.vehicle_id)
        if vehicle:
            vehicle.remove_imagem(image.filename)
        
        # Remover do banco
        db.session.delete(image)
        db.session.commit()
        
        return jsonify({'message': 'Imagem removida com sucesso'}), 200
        
    except Exception as e:
        return jsonify({'error': 'Erro interno do servidor'}), 500

@uploads_bp.route('/uploads/<int:vehicle_id>/reorder', methods=['PUT'])
@require_admin()
def reorder_images(vehicle_id):
    """
    Reordena as imagens de um veículo
    Requer autenticação de administrador
    """
    try:
        vehicle = Vehicle.query.get(vehicle_id)
        if not vehicle:
            return jsonify({'error': 'Veículo não encontrado'}), 404
        
        data = request.get_json()
        image_order = data.get('image_order', [])
        
        if not isinstance(image_order, list):
            return jsonify({'error': 'Ordem das imagens deve ser uma lista'}), 400
        
        # Atualizar ordem das imagens
        for index, image_id in enumerate(image_order):
            image = VehicleImage.query.filter_by(id=image_id, vehicle_id=vehicle_id).first()
            if image:
                image.image_order = index
        
        db.session.commit()
        
        return jsonify({'message': 'Ordem das imagens atualizada com sucesso'}), 200
        
    except Exception as e:
        return jsonify({'error': 'Erro interno do servidor'}), 500

@uploads_bp.route('/uploads/bulk', methods=['POST'])
@require_admin()
def bulk_upload():
    """
    Upload múltiplo de imagens para um veículo
    Requer autenticação de administrador
    """
    try:
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
                
                # Verificar tamanho
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)
                
                if file_size > MAX_FILE_SIZE:
                    errors.append(f'{file.filename}: Arquivo muito grande')
                    continue
                
                # Processar upload (código similar ao upload simples)
                upload_dir = create_upload_directory()
                filename = generate_unique_filename(file.filename)
                file_path = os.path.join(upload_dir, filename)
                
                file.save(file_path)
                
                if not validate_image(file_path):
                    os.remove(file_path)
                    errors.append(f'{file.filename}: Não é uma imagem válida')
                    continue
                
                # Criar versões redimensionadas
                original_path = os.path.join(upload_dir, f"original_{filename}")
                medium_path = os.path.join(upload_dir, f"medium_{filename}")
                thumb_path = os.path.join(upload_dir, f"thumb_{filename}")
                
                resize_image(file_path, original_path, (1920, 1080))
                resize_image(file_path, medium_path, IMAGE_SIZES['medium'])
                resize_image(file_path, thumb_path, IMAGE_SIZES['thumbnail'])
                
                os.remove(file_path)
                
                # Salvar no banco
                vehicle_image = VehicleImage(
                    vehicle_id=vehicle_id,
                    filename=filename,
                    original_filename=secure_filename(file.filename),
                    file_path=f"uploads/{filename}",
                    file_size=file_size,
                    mime_type=file.content_type,
                    image_order=len(vehicle.vehicle_images) + len(uploaded_images)
                )
                
                db.session.add(vehicle_image)
                vehicle.add_imagem(filename)
                
                uploaded_images.append(vehicle_image.to_dict())
                
            except Exception as e:
                errors.append(f'{file.filename}: Erro ao processar')
        
        db.session.commit()
        
        return jsonify({
            'message': f'{len(uploaded_images)} imagens enviadas com sucesso',
            'uploaded_images': uploaded_images,
            'errors': errors
        }), 201 if uploaded_images else 400
        
    except Exception as e:
        return jsonify({'error': 'Erro interno do servidor'}), 500

