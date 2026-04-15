from typing import Optional

from pydantic import BaseModel


class CarSeriesOut(BaseModel):
    id: int
    name: str


class EcuModelOut(BaseModel):
    id: int
    car_series_id: int
    name: str


class IdentifyRuleOut(BaseModel):
    id: int
    ecu_model_id: int
    addr: int
    data_length: int
    hex_value: str


class FunctionOut(BaseModel):
    id: int
    ecu_model_id: int
    name: str
    success_msg: Optional[str] = None


class PatchOut(BaseModel):
    id: int
    seq_no: int
    addr: int
    data_length: int
    value_hex: str


class FunctionPatchesOut(BaseModel):
    function_id: int
    function_name: str
    identify_hex: str
    success_msg: Optional[str] = None
    patches: list[PatchOut]


class CpuChecksumOut(BaseModel):
    id: int
    cpu_key: str
    cpu_display_name: str
    checksum_addr: int


class AppWiringGuideOut(BaseModel):
    id: int
    name: str
    model: Optional[str] = None
    car_model: Optional[str] = None
    keywords: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    button_text: Optional[str] = None
    file_name: Optional[str] = None
    url: Optional[str] = None


class LearningArticleOut(BaseModel):
    id: int
    title: str
    summary: Optional[str] = None
    cover_image_url: Optional[str] = None
    content_html: Optional[str] = None


class HealthOut(BaseModel):
    status: str
    app: str
