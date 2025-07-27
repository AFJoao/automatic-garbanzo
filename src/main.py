"""
Aplicação principal Flask para sistema de concessionária de veículos
Configurado para deploy no Render com CORS e autenticação JWT
"""
import os
import sys
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from datetime import timedelta

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Importar modelos
from src.models.user import db, User
from src.models.vehicle import Vehicle, VehicleImage

# Importar blueprints
from src.routes.auth import auth_bp
from src.routes.vehicles import vehicles_bp
from src.routes.uploads import uploads_bp

def create_app():
    """Factory function para criar a aplicação Flask"""
    app = Flask(__name__)
    
    # ==================== CONFIGURAÇÕES ====================
    
    # Configurações de segurança
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sua-chave-secreta-super-forte-aqui-mude-em-producao')
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'jwt-chave-secreta-super-forte-aqui-mude-em-producao')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
    app.config['JWT_ALGORITHM'] = 'HS256'
    
    # Configuração do banco de dados
    database_url = os.environ['DATABASE_URL']
    if database_url.startswith('postgres://'):
     database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    
    # Configurações de upload
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB
    
    # ==================== EXTENSÕES ====================
    
    # JWT
    jwt = JWTManager(app)
    
    # CORS - Permitir todas as origens para desenvolvimento e deploy
    CORS(app, 
         origins="*",
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    
    # Inicializar banco de dados
    db.init_app(app)
    
    # ==================== BLUEPRINTS ====================
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(vehicles_bp, url_prefix='/api')
    app.register_blueprint(uploads_bp, url_prefix='/api')
    
    # ==================== HANDLERS JWT ====================
    
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({'error': 'Token expirado'}), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({'error': 'Token inválido'}), 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({'error': 'Token de acesso necessário'}), 401
    
    # ==================== ROTA DE SAÚDE ====================
    
    @app.route('/api/health')
    def health_check():
        """Endpoint de verificação de saúde da aplicação"""
        return jsonify({
            'status': 'healthy',
            'message': 'API da Concessionária funcionando',
            'version': '1.0.0'
        }), 200
    
    # ==================== TRATAMENTO DE ERROS ====================
    
    @app.errorhandler(413)
    def too_large(e):
        return jsonify({'error': 'Arquivo muito grande (máximo 5MB)'}), 413
    
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Recurso não encontrado'}), 404
    
    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({'error': 'Erro interno do servidor'}), 500
    
    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({'error': 'Método não permitido'}), 405
    
    # ==================== INICIALIZAÇÃO DO BANCO ====================
    
    with app.app_context():
        # Criar tabelas
        db.create_all()
        
        # Criar usuário admin padrão se não existir
        admin_user = User.query.filter_by(email='admin@concessionaria.com').first()
        if not admin_user:
            admin_user = User(
                email='admin@concessionaria.com',
                role='admin'
            )
            admin_user.set_password('admin123')  # MUDE ESTA SENHA EM PRODUÇÃO!
            db.session.add(admin_user)
            db.session.commit()
            print("✅ Usuário admin criado: admin@concessionaria.com / admin123")
    
    return app

# Criar aplicação
app = create_app()

if __name__ == '__main__':
    # Configuração para desenvolvimento e deploy
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"🚀 Iniciando servidor na porta {port}")
    print(f"🔧 Modo debug: {debug}")
    print(f"📊 Admin: admin@concessionaria.com / admin123")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )

