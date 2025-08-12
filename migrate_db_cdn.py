"""
Script de migração para adicionar campos do CDN ao banco de dados
Adiciona colunas cdn_file_id e cdn_url à tabela vehicle_images
"""
import os
import sys
from sqlalchemy import text

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(__file__))

from src.models.user import db
from src.main import create_app

def migrate_database():
    """Executa a migração do banco de dados"""
    app = create_app()
    
    with app.app_context():
        try:
            # Verificar se as colunas já existem
            result = db.engine.execute(text("PRAGMA table_info(vehicle_images)"))
            columns = [row[1] for row in result]
            
            # Adicionar coluna cdn_file_id se não existir
            if 'cdn_file_id' not in columns:
                print("Adicionando coluna cdn_file_id...")
                db.engine.execute(text("ALTER TABLE vehicle_images ADD COLUMN cdn_file_id VARCHAR(255)"))
                print("✅ Coluna cdn_file_id adicionada com sucesso")
            else:
                print("ℹ️ Coluna cdn_file_id já existe")
            
            # Adicionar coluna cdn_url se não existir
            if 'cdn_url' not in columns:
                print("Adicionando coluna cdn_url...")
                db.engine.execute(text("ALTER TABLE vehicle_images ADD COLUMN cdn_url VARCHAR(1000)"))
                print("✅ Coluna cdn_url adicionada com sucesso")
            else:
                print("ℹ️ Coluna cdn_url já existe")
            
            # Commit das alterações
            db.session.commit()
            print("✅ Migração concluída com sucesso!")
            
        except Exception as e:
            print(f"❌ Erro na migração: {e}")
            db.session.rollback()
            return False
    
    return True

if __name__ == '__main__':
    print("🔄 Iniciando migração do banco de dados para suporte a CDN...")
    success = migrate_database()
    
    if success:
        print("🎉 Migração concluída! O banco agora suporta CDN ImageKit.")
    else:
        print("💥 Falha na migração. Verifique os logs de erro.")
        sys.exit(1)

