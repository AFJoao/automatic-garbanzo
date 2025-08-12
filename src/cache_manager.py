"""
Sistema de cache em memória para otimização de consultas
Usa Flask-Caching com SimpleCache para evitar dependências externas
"""
import os
import time
import hashlib
from functools import wraps
from flask import request, current_app
from flask_caching import Cache

# Instância global do cache
cache = Cache()

def init_cache(app):
    """Inicializa o sistema de cache com a aplicação Flask"""
    # Configuração do cache
    cache_config = {
        'CACHE_TYPE': 'SimpleCache',  # Cache em memória
        'CACHE_DEFAULT_TIMEOUT': int(os.environ.get('CACHE_TIMEOUT', 3600)),  # 1 hora por padrão
        'CACHE_THRESHOLD': int(os.environ.get('CACHE_THRESHOLD', 500)),  # Máximo 500 itens
    }
    
    app.config.update(cache_config)
    cache.init_app(app)
    
    print(f"✅ Cache inicializado: {cache_config['CACHE_TYPE']}")
    print(f"   Timeout padrão: {cache_config['CACHE_DEFAULT_TIMEOUT']}s")
    print(f"   Limite de itens: {cache_config['CACHE_THRESHOLD']}")

def generate_cache_key(*args, **kwargs):
    """Gera uma chave única para o cache baseada nos argumentos"""
    # Incluir URL da requisição se disponível
    url_part = ""
    if request:
        url_part = request.path + "?" + request.query_string.decode('utf-8')
    
    # Combinar todos os argumentos
    key_parts = [url_part] + list(args) + [f"{k}={v}" for k, v in sorted(kwargs.items())]
    key_string = "|".join(str(part) for part in key_parts)
    
    # Gerar hash MD5 para chave compacta
    return hashlib.md5(key_string.encode('utf-8')).hexdigest()

def cache_vehicles_list(timeout=3600):
    """
    Decorator para cachear lista de veículos
    Timeout padrão: 1 hora
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Gerar chave do cache
            cache_key = f"vehicles_list_{generate_cache_key(*args, **kwargs)}"
            
            # Tentar obter do cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                current_app.logger.info(f"Cache HIT: {cache_key}")
                return cached_result
            
            # Executar função e cachear resultado
            current_app.logger.info(f"Cache MISS: {cache_key}")
            result = f(*args, **kwargs)
            
            # Cachear apenas se o resultado for válido
            if result and (isinstance(result, (list, dict)) or hasattr(result, 'status_code')):
                cache.set(cache_key, result, timeout=timeout)
                current_app.logger.info(f"Cache SET: {cache_key} (timeout: {timeout}s)")
            
            return result
        return decorated_function
    return decorator

def cache_vehicle_detail(timeout=7200):
    """
    Decorator para cachear detalhes de um veículo específico
    Timeout padrão: 2 horas (veículos mudam menos frequentemente)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Extrair ID do veículo dos argumentos
            vehicle_id = None
            if args:
                vehicle_id = args[0]
            elif 'vehicle_id' in kwargs:
                vehicle_id = kwargs['vehicle_id']
            elif 'id' in kwargs:
                vehicle_id = kwargs['id']
            
            # Gerar chave do cache
            cache_key = f"vehicle_detail_{vehicle_id}_{generate_cache_key(*args, **kwargs)}"
            
            # Tentar obter do cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                current_app.logger.info(f"Cache HIT: {cache_key}")
                return cached_result
            
            # Executar função e cachear resultado
            current_app.logger.info(f"Cache MISS: {cache_key}")
            result = f(*args, **kwargs)
            
            # Cachear apenas se o resultado for válido
            if result and (isinstance(result, (list, dict)) or hasattr(result, 'status_code')):
                cache.set(cache_key, result, timeout=timeout)
                current_app.logger.info(f"Cache SET: {cache_key} (timeout: {timeout}s)")
            
            return result
        return decorated_function
    return decorator

def invalidate_vehicle_cache(vehicle_id=None):
    """
    Invalida cache relacionado a veículos
    Se vehicle_id for fornecido, invalida apenas esse veículo
    Senão, invalida todo o cache de veículos
    """
    try:
        if vehicle_id:
            # Invalidar cache específico do veículo
            patterns = [
                f"vehicle_detail_{vehicle_id}_*",
                f"vehicles_list_*"  # Lista também precisa ser invalidada
            ]
            
            # Como SimpleCache não suporta wildcard, vamos limpar tudo
            cache.clear()
            current_app.logger.info(f"Cache invalidado para veículo {vehicle_id}")
        else:
            # Invalidar todo o cache
            cache.clear()
            current_app.logger.info("Todo o cache foi invalidado")
            
    except Exception as e:
        current_app.logger.error(f"Erro ao invalidar cache: {e}")

def cache_stats():
    """Retorna estatísticas do cache (limitado no SimpleCache)"""
    try:
        # SimpleCache não fornece estatísticas detalhadas
        return {
            'cache_type': 'SimpleCache',
            'status': 'active',
            'note': 'Estatísticas limitadas no SimpleCache'
        }
    except Exception as e:
        return {
            'cache_type': 'SimpleCache',
            'status': 'error',
            'error': str(e)
        }

def warm_cache():
    """
    Aquece o cache com dados frequentemente acessados
    Deve ser chamado após inicialização da aplicação
    """
    try:
        from src.models.vehicle import Vehicle
        
        # Pré-carregar lista de veículos ativos
        vehicles = Vehicle.query.filter_by(is_active=True).all()
        
        # Simular cache da lista
        cache_key = f"vehicles_list_{generate_cache_key('active=True')}"
        vehicles_data = [vehicle.to_dict() for vehicle in vehicles]
        cache.set(cache_key, vehicles_data, timeout=3600)
        
        current_app.logger.info(f"Cache aquecido com {len(vehicles)} veículos")
        
    except Exception as e:
        current_app.logger.error(f"Erro ao aquecer cache: {e}")

# Decorators específicos para diferentes tipos de consulta

def cache_active_vehicles(timeout=3600):
    """Cache específico para veículos ativos"""
    return cache_vehicles_list(timeout)

def cache_vehicles_by_category(timeout=3600):
    """Cache específico para veículos por categoria"""
    return cache_vehicles_list(timeout)

def cache_vehicles_search(timeout=1800):
    """Cache para resultados de busca (timeout menor - 30 min)"""
    return cache_vehicles_list(timeout)

# Context processor para templates (se necessário)
def cache_context_processor():
    """Adiciona informações de cache ao contexto dos templates"""
    return {
        'cache_stats': cache_stats(),
        'cache_enabled': True
    }

# Middleware para adicionar headers de cache
def add_cache_headers(response, timeout=3600):
    """Adiciona headers de cache HTTP à resposta"""
    if response.status_code == 200:
        response.headers['Cache-Control'] = f'public, max-age={timeout}'
        response.headers['Expires'] = time.strftime(
            '%a, %d %b %Y %H:%M:%S GMT', 
            time.gmtime(time.time() + timeout)
        )
    return response

