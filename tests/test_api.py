import io
from pathlib import Path
import pytest
from alembic.config import Config
from alembic import command
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from app.main import app
from app.importer import extract_pdf, local_normalize
from app.quantities import warnings,render

@pytest.fixture(scope='module')
def client():
    command.upgrade(Config('alembic.ini'),'head')
    with TestClient(app) as c:yield c

def test_crud_search_history_and_restore(client):
    r=client.post('/api/recipes',json={'title':'Verification soup','servings':2,'cuisine':'Italian','category':'Dinner','tags':['weeknight'],'dietary_tags':['vegan'],'total_minutes':20,'notes':'Freezes well','ingredients':[{'id':'oil','name':'olive oil','amount':{'quantity':1,'unit':'tbsp'}}],'steps':[{'text':'Add {{oil}}.','uses':[{'id':'oil','ingredient_id':'oil'}]}]})
    assert r.status_code==201,r.text
    id=r.json()['id'];url='/api/recipes/'+id
    data=client.get(url+'?factor=2&preference=metric').json()
    assert data['rendered']['servings']==4
    assert data['rendered']['ingredients'][0]['text']=='30 ml / 2 tbsp olive oil'
    assert data['rendered']['steps'][0]['text']=='Add 30 ml / 2 tbsp olive oil.'
    for q in ['soup','olive','weeknight','Italian','Freezes']:
        assert id in [x['id'] for x in client.get('/api/recipes',params={'q':q}).json()]
    assert client.get('/api/recipes?diet=vegan&max_minutes=30&category=Dinner').json()
    body=data['recipe'];body['title']='Updated soup';assert client.put(url,json=body).status_code==200
    assert client.post(url+'/history',json={'date':'2026-09-19','note':'More lemon next time','rating':4}).status_code==200
    assert client.get(url).json()['history'][0]['rating']==4
    assert client.delete(url).status_code==200
    assert client.get(url).status_code==404
    assert any(x['id']==id for x in client.get('/api/recipes?trash=true').json())
    assert client.post(url+'/restore').status_code==200
    assert client.get(url).json()['recipe']['title']=='Updated soup'

def test_import_text_original_and_diagnostics(client):
    text='Simple oil\nIngredients\n1 tbsp olive oil\nInstructions\nAdd olive oil (1 tbsp).'
    response=client.post('/api/import',json={'text':text})
    assert response.status_code==201,response.text
    data=response.json()
    assert client.get(data['source']['file']).text==text
    diag=client.get(data['source']['diagnostics']).json()
    assert diag['method']=='local' and diag['extracted_text']==text

def test_pdf_fixture():
    path=Path('tests/fixtures/Sweet Potato One Pan Bake.pdf')
    if not path.exists():pytest.skip('Private reference PDF not supplied; never committed to Git.')
    text,_=extract_pdf(path);r=local_normalize(text)
    assert r.title=='Sweet Potato One Pan Bake'
    assert len(r.ingredients)==22
    assert {i.group for i in r.ingredients}=={'Main','Sauce'}
    assert any(i.amount.maximum==2 for i in r.ingredients)
    assert any('Italian seasoning' in i.alternatives for i in r.ingredients)
    assert any(i.amount.text=='to taste' for i in r.ingredients)
    assert any('vinegar' in w and 'reconcile' in w for w in warnings(r))
    assert any('3 tbsp olive oil' in s['text'] for s in render(r,[],2,'us')['steps'])

def test_pdf_upload(client):
    path=Path('tests/fixtures/Sweet Potato One Pan Bake.pdf')
    if not path.exists():pytest.skip('Private reference PDF not supplied.')
    data=path.read_bytes()
    result=client.post('/api/import/file',files={'file':(path.name,data,'application/pdf')})
    assert result.status_code==201,result.text
    source=result.json()['source'];assert client.get(source['file']).content==data
    assert result.json()['recipe']['ingredients']

def test_photo_upload(client):
    r=client.post('/api/recipes',json={'title':'Photo test'}).json()
    im=Image.new('RGB',(120,80),'green');buffer=io.BytesIO();im.save(buffer,'PNG')
    result=client.post('/api/recipes/'+r['id']+'/image',files={'file':('photo.png',buffer.getvalue(),'image/png')})
    assert result.status_code==200
    assert client.get(result.json()['image']).headers['content-type']=='image/jpeg'

def test_conversion_edit_and_boundaries(client):
    r=client.post('/api/conversions',json={'name':'test flour','aliases':[],'grams_per_cup':130,'liquid':False})
    assert r.status_code==200
    id=r.json()['id']
    assert client.put('/api/conversions/'+str(id),json={'name':'test flour','grams_per_cup':140}).status_code==200
    assert client.delete('/api/conversions/'+str(id)).status_code==200
    assert client.post('/api/recipes',json={'title':'bad'},headers={'Origin':'https://untrusted.example'}).status_code==403
    assert client.get('/media/originals/../../.env').status_code==404
    assert client.post('/api/recipes',json={'title':'broken','steps':[{'text':'{{ghost}}'}]}).status_code==422

def test_image_and_scanned_pdf_import(client):
    im=Image.new('RGB',(1000,700),'white')
    ImageDraw.Draw(im).multiline_text((50,50),'OCR soup\n\nIngredients\n1 tbsp olive oil\n\nInstructions\nAdd olive oil (1 tbsp).',fill='black',font=ImageFont.load_default(size=32),spacing=12)
    for format,mime in [('PNG','image/png'),('PDF','application/pdf')]:
        buf=io.BytesIO();im.save(buf,format)
        result=client.post('/api/import/file',files={'file':('scan.'+format.lower(),buf.getvalue(),mime)})
        assert result.status_code==201,result.text
        recipe=result.json()['recipe']
        assert any('OCR' in w for w in recipe['import_warnings'])
        assert recipe['ingredients'][0]['amount']['quantity']==1

def test_url_recipe_jsonld(client,monkeypatch):
    import app.main as main
    html=b'<html><script type="application/ld+json">{"@type":"Recipe","name":"URL soup","recipeIngredient":["1 tbsp olive oil"],"recipeInstructions":[{"@type":"HowToStep","text":"Add olive oil (1 tbsp)."}],"totalTime":"PT20M"}</script></html>'
    monkeypatch.setattr(main,'fetch_url',lambda url:(html,'text/html',url))
    result=client.post('/api/import',json={'url':'https://example.com/recipe'})
    assert result.status_code==201,result.text
    data=result.json()
    assert data['recipe']['title']=='URL soup' and data['recipe']['total_minutes']==20
    assert data['source']['url']=='https://example.com/recipe'
    original=client.get(data['source']['file'])
    assert original.content==html and original.headers['content-type']=='application/octet-stream'
