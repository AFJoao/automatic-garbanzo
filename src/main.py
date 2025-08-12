"""
Aplicação principal Flask para sistema de concessionária de veículos
Configurado para deploy no Render com CORS, autenticação JWT, CDN ImageKit e Cache
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
from src.routes.vehicles_cached import vehicles_bp  # Versão com cache
from src.routes.uploads import uploads_bp
from src.routes.cdn_uploads import cdn_uploads_bp

# Importar sistema de cache
from src.cache_manager import init_cache, warm_cache, cache_context_processor

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
    database_url = os.environ.get('DATABASE_URL', 'sqlite:///concessionaria.db')

    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    # Troca para usar o driver psycopg3
    if database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Configurações de upload
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB
    
    # Configurações do ImageKit CDN
    app.config['IMAGEKIT_PRIVATE_KEY'] = os.environ.get('IMAGEKIT_PRIVATE_KEY', '')
    app.config['IMAGEKIT_PUBLIC_KEY'] = os.environ.get('IMAGEKIT_PUBLIC_KEY', '')
    app.config['IMAGEKIT_URL_ENDPOINT'] = os.environ.get('IMAGEKIT_URL_ENDPOINT', '')
    
    # Configurações de Cache
    app.config['CACHE_TIMEOUT'] = int(os.environ.get('CACHE_TIMEOUT', 3600))  # 1 hora
    app.config['CACHE_THRESHOLD'] = int(os.environ.get('CACHE_THRESHOLD', 500))  # 500 itens
    
    # ==================== EXTENSÕES ====================
    
    # JWT
    jwt = JWTManager(app)
    
    # CORS - Configuração mais permissiva para resolver problemas
    CORS(app, 
         resources={r"/*": {"origins": "*"}},
         allow_headers=["Content-Type", "Authorization", "Access-Control-Allow-Credentials"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         supports_credentials=True)
    
    # Inicializar sistema de cache
    init_cache(app)
    
    # Headers de segurança e CORS adicionais
    @app.after_request
    def add_security_headers(response):
        # Headers CORS adicionais
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        
        # Headers de segurança
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Headers de cache para recursos estáticos
        if request.endpoint and any(static in request.endpoint for static in ['static', 'uploads']):
            response.headers['Cache-Control'] = 'public, max-age=86400'  # 24 horas
        
        return response
    
    # Handler para requisições OPTIONS (preflight)
    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            response = jsonify({'status': 'ok'})
            response.headers.add("Access-Control-Allow-Origin", "*")
            response.headers.add('Access-Control-Allow-Headers', "Content-Type, Authorization")
            response.headers.add('Access-Control-Allow-Methods', "GET, POST, PUT, DELETE, OPTIONS")
            return response
    
    # Inicializar banco de dados
    db.init_app(app)
    
    # Context processor para cache
    app.context_processor(cache_context_processor)
    
    # ==================== BLUEPRINTS ====================
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(vehicles_bp, url_prefix='/api')  # Versão com cache
    app.register_blueprint(uploads_bp, url_prefix='/api')  # Upload local (mantido para compatibilidade)
    app.register_blueprint(cdn_uploads_bp, url_prefix='/api')  # Upload via CDN (novo)
    
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
        # Verificar configuração do CDN
        cdn_configured = all([
            app.config.get('IMAGEKIT_PRIVATE_KEY'),
            app.config.get('IMAGEKIT_PUBLIC_KEY'),
            app.config.get('IMAGEKIT_URL_ENDPOINT')
        ])
        
        # Verificar cache
        try:
            from src.cache_manager import cache_stats
            cache_status = cache_stats()
            cache_enabled = cache_status.get('status') == 'active'
        except Exception:
            cache_enabled = False
        
        return jsonify({
            'status': 'healthy',
            'message': 'API da Concessionária funcionando',
            'version': '1.2.0',
            'features': {
                'cdn_enabled': cdn_configured,
                'local_upload': True,
                'cache_enabled': cache_enabled,
                'cache_timeout': app.config.get('CACHE_TIMEOUT', 3600),
                'cache_threshold': app.config.get('CACHE_THRESHOLD', 500)
            }
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
        
        # Verificar se precisa executar migração para CDN
        try:
            from sqlalchemy import text
            result = db.engine.execute(text("PRAGMA table_info(vehicle_images)"))
            columns = [row[1] for row in result]
            
            if 'cdn_file_id' not in columns or 'cdn_url' not in columns:
                print("⚠️ Banco de dados precisa de migração para suporte a CDN")
                print("Execute: python migrate_db_cdn.py")
        except Exception as e:
            print(f"Aviso: Não foi possível verificar migração CDN: {e}")
        
        # Aquecer cache após inicialização
        try:
            warm_cache()
        except Exception as e:
            print(f"Aviso: Não foi possível aquecer cache: {e}")
    
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
    
    # Verificar configuração do CDN
    cdn_configured = all([
        os.environ.get('IMAGEKIT_PRIVATE_KEY'),
        os.environ.get('IMAGEKIT_PUBLIC_KEY'),
        os.environ.get('IMAGEKIT_URL_ENDPOINT')
    ])
    
    if cdn_configured:
        print("✅ CDN ImageKit configurado")
    else:
        print("⚠️ CDN ImageKit não configurado - configure as variáveis de ambiente")
        print("   IMAGEKIT_PRIVATE_KEY, IMAGEKIT_PUBLIC_KEY, IMAGEKIT_URL_ENDPOINT")
    
    # Verificar configuração do cache
    cache_timeout = os.environ.get('CACHE_TIMEOUT', 3600)
    cache_threshold = os.environ.get('CACHE_THRESHOLD', 500)
    print(f"🗄️ Cache configurado: timeout={cache_timeout}s, threshold={cache_threshold} itens")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )

