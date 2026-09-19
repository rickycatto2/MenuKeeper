"""Run once locally against the live app; reference PDFs are never committed."""
import sys
from pathlib import Path
import httpx
path=Path(sys.argv[1])
with httpx.Client(timeout=240) as client:
    result=client.post('http://localhost:5059/api/import/file',files={'file':(path.name,path.read_bytes(),'application/pdf')})
    result.raise_for_status()
    row=result.json()
    detail=client.get('http://localhost:5059/api/recipes/'+row['id']).json()
    diagnostic=client.get('http://localhost:5059'+row['source']['diagnostics']).json()
    print({'id':row['id'],'title':row['recipe']['title'],'ingredients':len(row['recipe']['ingredients']),'steps':len(row['recipe']['steps']),'method':diagnostic['method'],'errors':diagnostic['errors'],'warnings':detail['warnings']})
