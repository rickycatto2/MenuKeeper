import json
import os
import re
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, urljoin
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from PIL import Image, ImageOps
from app.db import DATA, Session, RecipeRow, HistoryRow, ConversionRow, now
from app.schema import Recipe, Conversion
from app.quantities import render, warnings
from app.importer import extract_pdf, ocr, fetch_url, html_text, normalize_recipe, MAX_BYTES

app=FastAPI(title='MenuKeeper',version='1.0.0')
STATIC=Path(__file__).parent/'static'
app.mount('/static',StaticFiles(directory=STATIC),name='static')

@app.middleware('http')
async def boundaries(request:Request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        allowed={os.environ.get('PUBLIC_ORIGIN','https://recipes.pixelwood.co'),'http://localhost:5059','http://127.0.0.1:5059'}
        if origin and origin not in allowed:return JSONResponse({'detail':'Cross-origin changes are not allowed.'},403)
        if int(request.headers.get('content-length','0'))>MAX_BYTES+65536:return JSONResponse({'detail':'Maximum upload size is 20 MB.'},413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response

@app.get('/')
def index():return FileResponse(STATIC/'index.html')
@app.get('/api/health')
def health():
    with Session() as db:db.execute(select(RecipeRow.id).limit(1))
    return {'status':'ok','ai_enabled':bool(os.environ.get('OPENAI_API_KEY','').strip())}

def household():
    # Single authorization boundary to replace when accounts are introduced.
    return 'home'
def find(db,id,deleted=False):
    row=db.get(RecipeRow,id)
    if not row or row.household_id!=household() or (row.deleted_at and not deleted):raise HTTPException(404,'Recipe not found')
    return row
def dictionary(db):return [r.body for r in db.scalars(select(ConversionRow))]
def search_text(r):
    return ' '.join([r.title,r.description,r.cuisine,r.category,r.notes,*r.tags,*r.dietary_tags,*[i.name+' '+i.preparation+' '+' '.join(i.alternatives) for i in r.ingredients]]).lower()
def payload(row):return {'id':row.id,'recipe':row.body,'source':row.source,'created_at':row.created_at,'updated_at':row.updated_at,'deleted_at':row.deleted_at}
def save_new(recipe,source=None):
    with Session() as db:
        row=RecipeRow(id=uuid.uuid4().hex,household_id=household(),body=recipe.model_dump(),search_text=search_text(recipe),source=source or {'type':'manual'})
        db.add(row);db.commit();db.refresh(row);return payload(row)

@app.get('/api/recipes')
def list_recipes(q:str='',tag:str='',diet:str='',cuisine:str='',category:str='',max_minutes:int|None=None,favorite:bool=False,trash:bool=False):
    with Session() as db:
        stmt=select(RecipeRow).where(RecipeRow.household_id==household()).order_by(RecipeRow.updated_at.desc())
        stmt=stmt.where(RecipeRow.deleted_at.is_not(None) if trash else RecipeRow.deleted_at.is_(None))
        for word in q.lower().split():stmt=stmt.where(RecipeRow.search_text.contains(word,autoescape=True))
        rows=db.scalars(stmt).all();result=[]
        for row in rows:
            r=row.body
            if tag and tag.lower() not in [t.lower() for t in r['tags']]:continue
            if diet and diet.lower() not in [t.lower() for t in r['dietary_tags']]:continue
            if cuisine and cuisine.lower() not in r['cuisine'].lower():continue
            if category and category.lower()!=r['category'].lower():continue
            if favorite and not r['favorite']:continue
            if max_minutes is not None and (r['total_minutes'] is None or r['total_minutes']>max_minutes):continue
            result.append(payload(row))
        return result
@app.post('/api/recipes',status_code=201)
def create(recipe:Recipe):return save_new(recipe)
@app.get('/api/recipes/{id}')
def detail(id:str,factor:float=Query(1,gt=0,le=100),preference:str=Query('metric',pattern='^(metric|us)$')):
    with Session() as db:
        row=find(db,id);r=Recipe.model_validate(row.body)
        history=[{'id':h.id,'date':h.date,'note':h.note,'rating':h.rating} for h in db.scalars(select(HistoryRow).where(HistoryRow.recipe_id==id).order_by(HistoryRow.date.desc(),HistoryRow.id.desc()))]
        return {**payload(row),'rendered':render(r,dictionary(db),factor,preference),'warnings':warnings(r),'history':history}
@app.put('/api/recipes/{id}')
def update(id:str,recipe:Recipe):
    with Session() as db:
        row=find(db,id);row.body=recipe.model_dump();row.search_text=search_text(recipe);row.updated_at=now();db.commit();return payload(row)
@app.delete('/api/recipes/{id}')
def delete(id:str):
    with Session() as db:
        row=find(db,id);row.deleted_at=now();db.commit()
    return {'ok':True,'message':'Moved to Recently deleted. Restore at any time; no automatic purge in v1.'}
@app.post('/api/recipes/{id}/restore')
def restore(id:str):
    with Session() as db:
        row=find(db,id,True);row.deleted_at=None;row.updated_at=now();db.commit();return payload(row)
class History(BaseModel):
    date:date
    note:str=''
    rating:int|None=Field(default=None,ge=1,le=5)
@app.post('/api/recipes/{id}/history')
def made(id:str,entry:History):
    with Session() as db:
        row=find(db,id)
        db.add(HistoryRow(recipe_id=id,date=entry.date.isoformat(),note=entry.note,rating=entry.rating))
        if entry.rating:row.body={**row.body,'rating':entry.rating}
        row.updated_at=now();db.commit()
    return {'ok':True}
@app.get('/api/conversions')
def conversions():
    with Session() as db:return [{'id':r.id,**r.body} for r in db.scalars(select(ConversionRow))]
@app.post('/api/conversions')
def add_conversion(c:Conversion):
    with Session() as db:
        row=ConversionRow(body=c.model_dump());db.add(row);db.commit();return {'id':row.id,**row.body}
@app.put('/api/conversions/{id}')
def edit_conversion(id:int,c:Conversion):
    with Session() as db:
        row=db.get(ConversionRow,id)
        if not row:raise HTTPException(404,'Conversion not found')
        row.body=c.model_dump();db.commit();return {'id':id,**row.body}
@app.delete('/api/conversions/{id}')
def delete_conversion(id:int):
    with Session() as db:
        row=db.get(ConversionRow,id)
        if not row:raise HTTPException(404,'Conversion not found')
        db.delete(row);db.commit()
    return {'ok':True}

def image_save(path):
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im);im.thumbnail((1600,1600))
        name=uuid.uuid4().hex+'.jpg';im.convert('RGB').save(DATA/'images'/name,quality=88)
    return '/media/images/'+name
async def uploaded(file):
    data=await file.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise HTTPException(413,'Maximum upload size is 20 MB.')
    ext=Path(file.filename or '').suffix.lower()
    if ext not in ('.pdf','.jpg','.jpeg','.png','.webp','.heic','.tif','.tiff'):raise HTTPException(400,'Upload a PDF, JPEG, PNG, WebP or TIFF file. Export HEIC as JPEG if unsupported.')
    name=uuid.uuid4().hex+ext;path=DATA/'originals'/name;path.write_bytes(data)
    return path,{'type':'pdf' if ext=='.pdf' else 'image','filename':file.filename,'file':'/media/originals/'+name}
def import_finish(text,source,extra_warnings=None,metadata=None,image_url=''):
    recipe,diag=normalize_recipe(text)
    recipe.import_warnings.extend(extra_warnings or [])
    if len(text)>100000:recipe.import_warnings.append('Source exceeds the AI text limit; only the first 100,000 characters were normalized. Review the original.')
    if image_url:recipe.image=image_url
    if metadata:
        recipe.description=recipe.description or BeautifulText(metadata.get('description',''))
        for key,field in [('prepTime','prep_minutes'),('cookTime','cook_minutes'),('totalTime','total_minutes')]:
            m=re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?',str(metadata.get(key,'')))
            if m and getattr(recipe,field) is None:setattr(recipe,field,int(m[1] or 0)*60+int(m[2] or 0))
        recipe.yield_text=recipe.yield_text or str(metadata.get('recipeYield',''))
    name=uuid.uuid4().hex+'.json'
    diagnostics={'extracted_text':text,'normalized_recipe':recipe.model_dump(),'validation_warnings':warnings(recipe),**diag}
    (DATA/'diagnostics'/name).write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2),encoding='utf-8')
    source['diagnostics']='/media/diagnostics/'+name
    return save_new(recipe,source)
def BeautifulText(text):
    from bs4 import BeautifulSoup
    return BeautifulSoup(str(text),'html.parser').get_text(' ',strip=True)
class ImportRequest(BaseModel):
    text:str=Field(default='',max_length=100000)
    url:str=Field(default='',max_length=3000)
@app.post('/api/import',status_code=201)
def import_text(body:ImportRequest):
    if not body.text.strip() and not body.url:raise HTTPException(400,'Paste recipe text or supply a URL.')
    source={'type':'text'};extra=[];metadata={};image_url=''
    if body.url:
        source={'type':'url','url':body.url}
        try:
            data,content_type,final=fetch_url(body.url)
            name=uuid.uuid4().hex
            if 'application/pdf' in content_type or data.startswith(b'%PDF'):
                path=DATA/'originals'/(name+'.pdf');path.write_bytes(data)
                source['file']='/media/originals/'+path.name
                text,extra=extract_pdf(path)
            else:
                path=DATA/'originals'/(name+'.html');path.write_bytes(data)
                source['file']='/media/originals/'+path.name
                text,metadata,remote_image=html_text(data)
                if remote_image:
                    try:
                        image_data,_,_=fetch_url(urljoin(final,remote_image));ip=DATA/'originals'/(name+'.image');ip.write_bytes(image_data);image_url=image_save(ip)
                    except Exception:extra.append('Source image could not be saved. You can upload a photo.')
            source['resolved_url']=final
        except Exception as e:
            # Retain failed URL attempt and error class without logging sensitive provider details.
            name=uuid.uuid4().hex+'.json'
            (DATA/'diagnostics'/name).write_text(json.dumps({'source':source,'error':type(e).__name__}),encoding='utf-8')
            raise HTTPException(400,'Could not fetch or extract this public recipe URL. Try pasting its text or uploading a PDF.')
    else:
        text=body.text
        path=DATA/'originals'/(uuid.uuid4().hex+'.txt');path.write_text(text,encoding='utf-8');source['file']='/media/originals/'+path.name
    return import_finish(text,source,extra,metadata,image_url)
@app.post('/api/import/file',status_code=201)
async def import_file(file:UploadFile=File(...)):
    path,source=await uploaded(file)
    return await run_in_threadpool(import_saved_file,path,source)

def import_saved_file(path,source):
    extra=[]
    try:
        if source['type']=='pdf':text,extra=extract_pdf(path)
        else:
            text=ocr(path);extra=['Image OCR was used. Check all quantities against the original.']
        return import_finish(text,source,extra)
    except Exception as e:
        return import_finish('',source,['Source extraction failed ('+type(e).__name__+'). The original was saved; please fill in the recipe manually.'])
@app.post('/api/recipes/{id}/image')
async def upload_image(id:str,file:UploadFile=File(...)):
    with Session() as db:find(db,id)
    path,source=await uploaded(file)
    try:url=image_save(path)
    except Exception:raise HTTPException(400,'Image could not be read. Please use JPEG, PNG or WebP.')
    with Session() as db:
        row=find(db,id);row.body={**row.body,'image':url};row.updated_at=now();db.commit()
    return {'image':url}
@app.get('/media/{folder}/{name}')
def media(folder:str,name:str):
    if folder not in ('originals','images','diagnostics') or not re.fullmatch(r'[a-f0-9]{32}\.[a-z0-9]+',name):raise HTTPException(404)
    path=DATA/folder/name
    if not path.is_file():raise HTTPException(404)
    # HTML originals are downloads, never executable pages on the app origin.
    if path.suffix=='.html':return FileResponse(path,media_type='application/octet-stream',filename='original-source.html')
    return FileResponse(path)
