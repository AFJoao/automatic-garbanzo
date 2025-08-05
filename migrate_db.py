"""
Script de migração para adicionar a coluna 'sob_consulta' ao modelo Vehicle
Execute este script uma vez para atualizar o banco de dados em produção
"""
import os
import sys
from sqlalchemy import text

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(__file__))

from src.models.user import db
from src.models.vehicle import Vehicle
from src.main import create_app

def migrate_database():
    """Executa a migração do banco de dados"""
    app = create_app()
    
    with app.app_context():
        try:
            # Verificar se a coluna já existe
            result = db.session.execute(text("PRAGMA table_info(vehicles)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'sob_consulta' not in columns:
                print("Adicionando coluna 'sob_consulta' à tabela vehicles...")
                
                # Adicionar a coluna sob_consulta
                db.session.execute(text("ALTER TABLE vehicles ADD COLUMN sob_consulta BOOLEAN DEFAULT 0"))
                
                # Atualizar todos os registros existentes para sob_consulta = False
                db.session.execute(text("UPDATE vehicles SET sob_consulta = 0 WHERE sob_consulta IS NULL"))
                
                db.session.commit()
                print("✅ Migração concluída com sucesso!")
            else:
                print("✅ Coluna 'sob_consulta' já existe. Nenhuma migração necessária.")
                
        except Exception as e:
            print(f"❌ Erro durante a migração: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate_database()

