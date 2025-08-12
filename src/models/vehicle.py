"""
Modelo de veículo atualizado para o sistema de concessionária
Inclui suporte a CDN ImageKit
"""
from datetime import datetime
import json
from src.models.user import db  # Usar a mesma instância do db

class Vehicle(db.Model):
    """Modelo de veículo com todos os campos necessários"""
    __tablename__ = 'vehicles'
    
    id = db.Column(db.Integer, primary_key=True)
    marca = db.Column(db.String(100), nullable=False, index=True)
    modelo = db.Column(db.String(100), nullable=False, index=True)
    ano = db.Column(db.Integer, nullable=False, index=True)
    preco = db.Column(db.Float, nullable=True, index=True)
    sob_consulta = db.Column(db.Boolean, default=False, nullable=False)
    descricao = db.Column(db.Text)
    combustivel = db.Column(db.String(50), index=True)
    cambio = db.Column(db.String(50))
    cor = db.Column(db.String(50))
    quilometragem = db.Column(db.Integer, default=0)
    categoria = db.Column(db.String(50), index=True)
    whatsapp_link = db.Column(db.String(500))  # Link do WhatsApp para contato
    imagens = db.Column(db.Text)  # JSON string com array de URLs do CDN
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamento com imagens
    vehicle_images = db.relationship('VehicleImage', backref='vehicle', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        """Converte o veículo para dicionário"""
        return {
            'id': str(self.id),
            'marca': self.marca,
            'modelo': self.modelo,
            'ano': self.ano,
            'preco': self.preco if self.preco is not None else None,
            'sob_consulta': self.sob_consulta,
            'descricao': self.descricao,
            'combustivel': self.combustivel,
            'cambio': self.cambio,
            'cor': self.cor,
            'quilometragem': self.quilometragem,
            'categoria': self.categoria,
            'whatsapp_link': self.whatsapp_link,
            'imagens': self.get_imagens(),
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def set_imagens(self, imagens_list):
        """Define as imagens como JSON string - agora suporta URLs do CDN"""
        if imagens_list:
            self.imagens = json.dumps(imagens_list)
        else:
            self.imagens = None
    
    def get_imagens(self):
        """Retorna as imagens como lista - agora retorna URLs do CDN"""
        if self.imagens:
            try:
                return json.loads(self.imagens)
            except (json.JSONDecodeError, TypeError):
                return []
        return []
    
    def add_imagem(self, image_url):
        """Adiciona uma URL de imagem do CDN à lista"""
        imagens = self.get_imagens()
        if image_url not in imagens:
            imagens.append(image_url)
            self.set_imagens(imagens)
    
    def remove_imagem(self, image_url):
        """Remove uma URL de imagem do CDN da lista"""
        imagens = self.get_imagens()
        if image_url in imagens:
            imagens.remove(image_url)
            self.set_imagens(imagens)
    
    def __repr__(self):
        return f'<Vehicle {self.marca} {self.modelo} {self.ano}>'


class VehicleImage(db.Model):
    """Modelo atualizado para metadados das imagens dos veículos com suporte a CDN"""
    __tablename__ = 'vehicle_images'
    
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    image_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Novos campos para CDN
    cdn_file_id = db.Column(db.String(255))  # ID do arquivo no ImageKit
    cdn_url = db.Column(db.String(1000))     # URL completa do CDN
    
    def to_dict(self):
        """Converte a imagem para dicionário com suporte a CDN"""
        base_dict = {
            'id': self.id,
            'vehicle_id': self.vehicle_id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'image_order': self.image_order,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        
        # Se tiver URL do CDN, usar ela; senão, usar URL local
        if hasattr(self, 'cdn_url') and self.cdn_url:
            base_dict['url'] = self.cdn_url
            base_dict['cdn_file_id'] = getattr(self, 'cdn_file_id', None)
            # Gerar URLs de diferentes tamanhos usando transformações do ImageKit
            base_dict['urls'] = {
                'original': self.cdn_url,
                'large': f"{self.cdn_url}?tr=w-1200,h-800,c-maintain_ratio",
                'medium': f"{self.cdn_url}?tr=w-800,h-600,c-maintain_ratio",
                'thumbnail': f"{self.cdn_url}?tr=w-300,h-200,c-maintain_ratio",
                'webp_medium': f"{self.cdn_url}?tr=w-800,h-600,c-maintain_ratio,f-webp",
                'webp_thumbnail': f"{self.cdn_url}?tr=w-300,h-200,c-maintain_ratio,f-webp"
            }
        else:
            # Fallback para URLs locais
            base_dict['url'] = f'/api/uploads/{self.filename}'
            base_dict['urls'] = {
                'original': f'/api/uploads/original_{self.filename}',
                'medium': f'/api/uploads/medium_{self.filename}',
                'thumbnail': f'/api/uploads/thumb_{self.filename}'
            }
        
        return base_dict
    
    def __repr__(self):
        return f'<VehicleImage {self.filename}>'

