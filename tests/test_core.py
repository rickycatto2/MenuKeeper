import pytest
from pydantic import ValidationError
from app.schema import Recipe, Ingredient, Amount, Step, Usage
from app.quantities import render, warnings, parse_amount
from app.importer import local_normalize, fetch_url

def oil_recipe():
    return Recipe(title='Split oil',servings=4,ingredients=[Ingredient(id='oil',name='olive oil',amount=Amount(quantity=3,unit='tbsp'))],steps=[Step(text='Add {{oil}}.',uses=[Usage(id='oil',ingredient_id='oil',mode='amount',amount=Amount(quantity=q,unit='tbsp'))]) for q in (1.5,.5,1)])
def test_split_scaling():
    r=oil_recipe();v=render(r,[],2,'us')
    assert v['ingredients'][0]['text']=='6 tbsp olive oil'
    assert [s['text'] for s in v['steps']]==['Add 3 tbsp olive oil.','Add 1 tbsp olive oil.','Add 2 tbsp olive oil.']
    assert not warnings(r)
def test_metric_liquids_and_no_invented_density():
    r=oil_recipe();d=[{'name':'olive oil','aliases':[],'liquid':True}]
    v=render(r,d,.5,'metric')
    assert '22.5 ml / 1.5 tbsp' in v['ingredients'][0]['text']
    assert '11.25 ml / 0.75 tbsp' in v['steps'][0]['text']
    r.ingredients[0].name='mystery powder';r.ingredients[0].amount=Amount(quantity=1,unit='cup')
    assert render(r,d)['ingredients'][0]['text']=='1 cup mystery powder'
def test_local_density_and_recipe_override():
    i=Ingredient(id='flour',name='flour',amount=Amount(quantity=1,unit='cup'))
    r=Recipe(title='Flour',ingredients=[i]);d=[{'name':'all-purpose flour','aliases':['flour'],'grams_per_cup':125}]
    assert render(r,d)['ingredients'][0]['text']=='125 g / 1 cup flour'
    i.equivalent=Amount(quantity=140,unit='g')
    assert render(r,d,2)['ingredients'][0]['text']=='280 g / 2 cup flour'
    r.steps=[Step(text='Use {{f}}',uses=[Usage(id='f',ingredient_id='flour',mode='amount',amount=Amount(quantity=70,unit='g'))])]
    assert render(r,d,2,'us')['steps'][0]['text']=='Use 1 cup / 140 g flour'
def test_ranges_and_fraction():
    a,tail=parse_amount('1 to 2 cups tomatoes')
    assert (a.quantity,a.maximum,a.unit,tail)==(1,2,'cup','tomatoes')
    a,_=parse_amount('1½ cups flour');assert a.quantity==1.5
    r=oil_recipe();r.steps=[Step(text='Use {{half}}',uses=[Usage(id='half',ingredient_id='oil',mode='fraction',fraction=.5)])]
    assert render(r,[],2)['steps'][0]['text']=='Use 3 tbsp olive oil'
def test_broken_links_rejected():
    with pytest.raises(ValidationError):Recipe(title='Bad',steps=[Step(text='Use {{bad}}',uses=[Usage(id='bad',ingredient_id='missing')])])
    with pytest.raises(ValidationError):Recipe(title='Bad',steps=[Step(text='Use {{bad}}')])
def test_conflict_preserved():
    r=oil_recipe();r.ingredients[0].amount.quantity=2
    assert any('do not exactly reconcile' in x for x in warnings(r))
    assert r.ingredients[0].amount.quantity==2
def test_local_groups_and_links():
    r=local_normalize('Example\nIngredients\n2 tbsp olive oil\n1 to 2 cups tomatoes, halved\nSauce\n1 tbsp olive oil\nInstructions\nToss tomatoes (1 to 2 cups) with olive oil (2 tbsp).\nStir yogurt with olive oil (1 tbsp).')
    assert len(r.ingredients)==3 and r.ingredients[2].group=='Sauce'
    assert r.ingredients[1].preparation=='halved'
    assert '4 tbsp olive oil' in render(r,[],2)['steps'][0]['text']
def test_ssrf_rejected():
    for url in ('http://127.0.0.1','http://169.254.169.254','file:///etc/passwd','http://localhost:5059'):
        with pytest.raises(ValueError):fetch_url(url)

def test_unlinked_quantities_warn():
    r=Recipe(title='Incomplete',steps=[Step(text='Add 2 tbsp butter.')])
    assert any('Step 1 contains a quantity outside' in w for w in warnings(r))
