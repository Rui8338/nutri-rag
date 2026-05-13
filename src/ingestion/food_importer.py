import re
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
            val = val.replace(',', '.')  # vírgula portuguesa → ponto
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def normalize_column(col: str) -> str:
    """
    Lowercase + colapsa qualquer whitespace múltiplo (incluindo \\n e tabs)
    num único espaço + strip. Crítico porque os headers do Excel INSA têm
    \\n e múltiplos espaços que destruíam o mapeamento na versão anterior.
    """
    return re.sub(r'\s+', ' ', str(col)).strip().lower()


def get_column(row, key: str, available_columns: set) -> object:
    """
    Como row.get(key), mas levanta KeyError se a coluna não existir.
    Fail-loud para evitar bugs silenciosos onde mismatch de schema
    se traduz em colunas a 0.
    """
    if key not in available_columns:
        raise KeyError(
            f"Coluna esperada não encontrada: {key!r}. "
            f"Colunas disponíveis ({len(available_columns)}): "
            f"{sorted(available_columns)}"
        )
    return row.get(key)


# Mapeamento source (Excel INSA, normalizado) -> destino (Food model)
COLUMN_MAPPING = {
    "name": "nome do alimento",
    "calories": "energia [kcal]",
    "protein_g": "proteínas [g]",
    "carbs_g": "hidratos de carbono [g]",
    "fat_g": "lípidos [g]",
    "fiber_g": "fibra [g]",
    "sodium_mg": "sódio [mg]",
    "water_g": "água [g]",
}


def import_insa_table(xlsx_path: str | Path) -> int:
    """
    Importa Tabela INSA para nutrition.foods.

    Estratégia:
    - Normaliza headers do Excel (lowercase, colapsa whitespace múltiplo)
    - Valida que TODAS as colunas esperadas existem antes de inserir
      (fail-loud previne bugs silenciosos onde rename de coluna no
      Excel se traduz em campos da DB a 0)
    """
    df = pd.read_excel(xlsx_path, sheet_name=0)

    # Normalização robusta — trata \n, espaços múltiplos, tabs, casing
    df.columns = [normalize_column(c) for c in df.columns]
    available = set(df.columns)
    logger.info(f"Colunas detectadas após normalização: {len(available)}")

    # Validação prévia — confirmar que todas as colunas esperadas existem
    expected_columns = set(COLUMN_MAPPING.values())
    missing = expected_columns - available
    if missing:
        raise KeyError(
            f"Colunas esperadas em falta no Excel: {sorted(missing)}. "
            f"Colunas disponíveis: {sorted(available)}"
        )

    session = SessionLocal()
    count_inserted = 0
    count_skipped = 0

    try:
        for idx, row in df.iterrows():
            if idx % 100 == 0:
                logger.info(f"A processar {idx}/{len(df)}...")

            try:
                name = str(get_column(row, COLUMN_MAPPING["name"], available)).strip()
                if not name or name.lower() == "nan":
                    count_skipped += 1
                    continue

                food = Food(
                    name=name,
                    portion_size_g=100.0,
                    calories=clean_float(get_column(row, COLUMN_MAPPING["calories"], available)),
                    protein_g=clean_float(get_column(row, COLUMN_MAPPING["protein_g"], available)),
                    carbs_g=clean_float(get_column(row, COLUMN_MAPPING["carbs_g"], available)),
                    fat_g=clean_float(get_column(row, COLUMN_MAPPING["fat_g"], available)),
                    fiber_g=clean_float(get_column(row, COLUMN_MAPPING["fiber_g"], available)),
                    sodium_mg=clean_float(get_column(row, COLUMN_MAPPING["sodium_mg"], available)),
                    water_g=clean_float(get_column(row, COLUMN_MAPPING["water_g"], available)),
                )

                session.add(food)
                count_inserted += 1
            except Exception as e:
                logger.warning(f"Linha {idx} ignorada: {e}")
                count_skipped += 1

        session.commit()
        logger.info(f"Importados {count_inserted} alimentos, ignorados {count_skipped}")
        return count_inserted

    except Exception as e:
        session.rollback()
        logger.error(f"Importação falhou: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    insa_path = settings.sources_dir / "INSA_Tabela_Composicao2.xlsx"
    import_insa_table(insa_path)