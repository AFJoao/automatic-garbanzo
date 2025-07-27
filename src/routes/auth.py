"""
Rotas de autenticação com JWT para administradores
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from marshmallow import Schema, fields, ValidationError, validate
from datetime import datetime, timedelta
from src.models.user import User, db

auth_bp = Blueprint('auth', __name__)

class LoginSchema(Schema):
    """Schema para validação de login"""
    email = fields.Email(required=True, validate=validate.Length(min=5, max=120))
    password = fields.Str(required=True, validate=validate.Length(min=6, max=100))

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Endpoint de login para administradores
    Retorna token JWT válido por 24 horas
    """
    try:
        # Validar dados de entrada
        schema = LoginSchema()
        data = schema.load(request.get_json() or {})
        
        # Buscar usuário no banco
        user = User.query.filter_by(email=data['email']).first()
        
        # Verificar credenciais
        if not user or not user.check_password(data['password']):
            return jsonify({'error': 'Email ou senha inválidos'}), 401
        
        # Verificar se usuário está ativo
        if not user.is_active:
            return jsonify({'error': 'Usuário inativo'}), 401
        
        # Criar token JWT com claims adicionais
        additional_claims = {
            'role': user.role,
            'user_id': user.id
        }
        
        access_token = create_access_token(
            identity=user.email,
            additional_claims=additional_claims,
            expires_delta=timedelta(hours=24)
        )
        
        # Atualizar último login
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'Login realizado com sucesso',
            'access_token': access_token,
            'user': user.to_dict()
        }), 200
        
    except ValidationError as e:
        return jsonify({'errors': e.messages}), 400
    except Exception as e:
        return jsonify({'error': 'Erro interno do servidor'}), 500

@auth_bp.route('/verify', methods=['GET'])
@jwt_required()
def verify_token():
    """
    Verifica se o token JWT é válido
    Retorna informações do usuário autenticado
    """
    try:
        current_user_email = get_jwt_identity()
        claims = get_jwt()
        
        # Buscar usuário atual
        user = User.query.filter_by(email=current_user_email).first()
        
        if not user or not user.is_active:
            return jsonify({'error': 'Usuário não encontrado ou inativo'}), 401
        
        return jsonify({
            'valid': True,
            'user': user.to_dict(),
            'claims': {
                'role': claims.get('role'),
                'user_id': claims.get('user_id')
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Token inválido'}), 401

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required()
def refresh_token():
    """
    Gera um novo token JWT para o usuário autenticado
    """
    try:
        current_user_email = get_jwt_identity()
        claims = get_jwt()
        
        # Buscar usuário atual
        user = User.query.filter_by(email=current_user_email).first()
        
        if not user or not user.is_active:
            return jsonify({'error': 'Usuário não encontrado ou inativo'}), 401
        
        # Criar novo token
        additional_claims = {
            'role': user.role,
            'user_id': user.id
        }
        
        new_token = create_access_token(
            identity=user.email,
            additional_claims=additional_claims,
            expires_delta=timedelta(hours=24)
        )
        
        return jsonify({
            'message': 'Token renovado com sucesso',
            'access_token': new_token
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Erro ao renovar token'}), 500

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout do usuário (no frontend, o token deve ser removido)
    """
    try:
        return jsonify({'message': 'Logout realizado com sucesso'}), 200
    except Exception as e:
        return jsonify({'error': 'Erro no logout'}), 500

# Função auxiliar para verificar se usuário é admin
def require_admin():
    """Decorator para verificar se o usuário é admin"""
    def decorator(f):
        from functools import wraps
        @wraps(f)
        @jwt_required()
        def decorated_function(*args, **kwargs):
            claims = get_jwt()
            if claims.get('role') != 'admin':
                return jsonify({'error': 'Acesso negado. Apenas administradores.'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

