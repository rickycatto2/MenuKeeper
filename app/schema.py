from typing import Literal
from pydantic import BaseModel, Field, model_validator
import re

class Amount(BaseModel):
    quantity: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    maximum: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    unit: str = Field(default='',description='Measurement unit only, e.g. cup, tbsp, tsp, g, ml, can. Do not use size adjectives like medium or whole.')
    text: str = Field(default='',description='Only an unmeasured qualifier such as to taste, pinch, or as needed. Never repeat the numeric quantity or unit here.')

    @model_validator(mode='after')
    def check_range(self):
        if self.maximum is not None and (self.quantity is None or self.maximum < self.quantity):
            raise ValueError('Range maximum must be at least the starting quantity')
        return self

class Ingredient(BaseModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$')
    name: str = Field(min_length=1)
    group: str = 'Main'
    amount: Amount = Field(default_factory=Amount)
    preparation: str = ''
    optional: bool = False
    alternatives: list[str] = Field(default_factory=list)
    equivalent: Amount | None = None

class Usage(BaseModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$')
    ingredient_id: str
    mode: Literal['all', 'amount', 'fraction', 'mention'] = 'all'
    amount: Amount | None = None
    fraction: float | None = Field(default=None, ge=0, le=1)
    alternative: str = ''

class Step(BaseModel):
    text: str = Field(description='Instruction template. Replace each ingredient name and its quantity by exactly one {{usage_id}} token. Example: Toss {{oil_use}} with {{potato_use}}. Do not leave ingredient names outside their tokens.')
    group: str = ''
    uses: list[Usage] = Field(default_factory=list,description='One record per {{usage_id}} token in text; its id must exactly match the token and ingredient_id must match a listed ingredient.')

class Recipe(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ''
    servings: float | None = Field(default=None, gt=0, le=10000)
    yield_text: str = ''
    prep_minutes: int | None = Field(default=None, ge=0)
    cook_minutes: int | None = Field(default=None, ge=0)
    total_minutes: int | None = Field(default=None, ge=0)
    image: str = ''
    category: str = ''
    cuisine: str = ''
    tags: list[str] = Field(default_factory=list)
    dietary_tags: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    notes: str = ''
    rating: int | None = Field(default=None, ge=1, le=5)
    favorite: bool = False
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    import_warnings: list[str] = Field(default_factory=list)
    dismissed_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def check_links(self):
        ids = [i.id for i in self.ingredients]
        if len(ids) != len(set(ids)):
            raise ValueError('Ingredient IDs must be unique')
        for step in self.steps:
            use_ids = [u.id for u in step.uses]
            if len(use_ids) != len(set(use_ids)):
                raise ValueError('Usage IDs must be unique within a step')
            tokens = re.findall(r'\{\{([a-zA-Z0-9_-]+)\}\}', step.text)
            if sorted(tokens) != sorted(use_ids):
                raise ValueError('Each ingredient reference must appear exactly once as {{usage_id}} in the step')
            for u in step.uses:
                if u.ingredient_id not in ids:
                    raise ValueError('A step references a missing ingredient')
                if u.mode == 'amount' and u.amount is None:
                    raise ValueError('An explicit use needs an amount')
                if u.mode == 'fraction' and u.fraction is None:
                    raise ValueError('A portion needs a fraction')
        return self

class Conversion(BaseModel):
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    grams_per_cup: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    liquid: bool = False
