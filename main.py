from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any

app = FastAPI()

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

# Suponha que você tem essas funções para manipular a planilha
from sheets_utils import get_sheet_data, update_sheet_cell

class UpdateCellRequest(BaseModel):
    row: int
    col: int
    value: str

@app.get("/api/sheet")
async def read_sheet():
    data = get_sheet_data()  # Retorna lista de dicionários (linhas)
    return data

@app.post("/api/sheet/update")
async def update_sheet(cell: UpdateCellRequest):
    success = update_sheet_cell(cell.row, cell.col, cell.value)
    if not success:
        raise HTTPException(status_code=500, detail="Erro ao atualizar a célula")
    return {"message": "Atualizado com sucesso"}
