from fastapi import APIRouter, HTTPException

from HEPiC.database.material_database import get_material_database

router = APIRouter()


def _db():
    return get_material_database()


@router.get("/")
def list_families():
    return {"families": _db().get_family_names()}


@router.get("/{family}")
def list_materials(family: str):
    db = _db()
    if family not in db.material_families:
        raise HTTPException(status_code=404, detail="Family not found")
    return {"pi_codes": db.get_pi_codes(family)}


@router.get("/{family}/{pi_code}")
def get_material(family: str, pi_code: str):
    material = _db().get_material(pi_code, family=family)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    return material
