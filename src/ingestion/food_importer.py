import pandas as pd
from pathlib import Path
from sqlalchemy.orm import Session
from src.database import Food, SessionLocal
from src.config import settings
import logging

logger = logging.getLogger(__name__)

def clean_float(val):
    """
    Converte valores para decimal de forma segura.
    Trata casos como 'tr' (traços), '-' ou células vazias que o INSA usa.
    """
    if pd.isna(val) or str(val).strip() in ["", "-", "tr", "vestígios"]:
        return 0.0
    try:
        if isinstance(val, str):
            val = val.replace(',', '.') # Garante que vírgulas viram pontos
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def import_insa_table(xlsx_path: str | Path) -> int:
    """
    Importa Tabela INSA para nutrition.foods.
    
    Espera colunas (case-insensitive): 
    nome, porção_g, calorias, proteína_g, hidratos_g, gordura_g, fibra_g, sódio_mg, água_g
    """
    df = pd.read_excel(xlsx_path, sheet_name=0)
    
    # Normalize column names (case-insensitive)
    df.columns = df.columns.str.lower().str.strip()
    df.columns = [col.replace('\n', ' ').strip().lower() for col in df.columns]
    
    logger.info(f"Colunas detetadas e normalizadas: {list(df.columns)}")
    
    session = SessionLocal()
    count_inserted = 0
    count_skipped = 0
    
    try:
        for idx, row in df.iterrows():
            if idx % 100 == 0:
                logger.info(f"Processing food {idx}/{len(df)}...")
            
            try:
                food = Food(
                    name=str(row.get('nome do alimento', '')).strip(),
                    portion_size_g=100.0,
                    calories=clean_float(row.get('energia [kcal]')),
                    protein_g=clean_float(row.get('proteínas [g]')),
                    carbs_g=clean_float(row.get('hidratos de carbono [g]')),
                    fat_g=clean_float(row.get('lípidos [g]')),
                    fiber_g=clean_float(row.get('fibra [g]')),
                    sodium_mg=clean_float(row.get('sódio [mg]')),
                    water_g=clean_float(row.get('água [g]'))
                )

                if not food.name:
                    continue

                session.add(food)
                count_inserted += 1
            except Exception as e:
                logger.warning(f"Skipped row {idx}: {e}")
                count_skipped += 1
        
        session.commit()
        logger.info(f"Imported {count_inserted} foods, skipped {count_skipped}")
        return count_inserted
    
    except Exception as e:
        session.rollback()
        logger.error(f"Import failed: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    insa_path = settings.sources_dir / "INSA_Tabela_Composicao2.xlsx"
    import_insa_table(insa_path)
