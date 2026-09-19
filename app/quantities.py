"""One deterministic quantity engine for both the list and step references."""
import re
from fractions import Fraction
from app.schema import Amount, Recipe

UNITS = {'cups':'cup','tablespoon':'tbsp','tablespoons':'tbsp','tbs':'tbsp','teaspoon':'tsp','teaspoons':'tsp','grams':'g','gram':'g','kilograms':'kg','milliliters':'ml','liters':'l','ounces':'oz','ounce':'oz','pounds':'lb','pound':'lb','cans':'can','cloves':'clove'}
VOLUME = {'cup':240, 'tbsp':15, 'tsp':5, 'ml':1, 'l':1000, 'fl oz':30, 'pint':480, 'quart':960}
WEIGHT = {'g':1, 'kg':1000, 'oz':28.349523125, 'lb':453.59237}
FRACTIONS = {'½':'1/2','¼':'1/4','¾':'3/4','⅓':'1/3','⅔':'2/3','⅛':'1/8','⅜':'3/8','⅝':'5/8','⅞':'7/8'}
NUM = r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)'
PREFIX = re.compile(r'^\s*(?P<a>'+NUM+r')(?:\s*(?:to|–|—|-)\s*(?P<b>'+NUM+r'))?\s*', re.I)

def unit(s):
    s = s.lower().strip().rstrip('.')
    return UNITS.get(s,s)
def number(s):
    return sum(float(Fraction(x)) for x in s.split())
def normalize(s):
    for a,b in FRACTIONS.items():
        s = re.sub(r'(\d)'+a, r'\1 '+b, s).replace(a,b)
    return s.strip()
def parse_amount(text):
    text = normalize(text)
    m = PREFIX.match(text)
    if not m:
        for word in ('to taste','a pinch of','a pinch','pinch','as needed'):
            if text.lower().startswith(word):
                return Amount(text='pinch' if 'pinch' in word else word), text[len(word):].strip()
        return Amount(),text
    tail = text[m.end():]
    words = tail.split(' ',1)
    candidate = unit(words[0]) if words else ''
    known = set(VOLUME)|set(WEIGHT)|{'can','clove','pinch','bunch','slice','piece'}
    if candidate in known:
        tail = words[1] if len(words)>1 else ''
    else:
        candidate = ''
    return Amount(quantity=number(m['a']),maximum=number(m['b']) if m['b'] else None,unit=candidate),tail.strip()
def fmt(n):
    if n is None: return ''
    if abs(n-round(n)) < .00001: return str(round(n))
    return f'{n:.3f}'.rstrip('0').rstrip('.')
def scaled(a, factor):
    return a.model_copy(update={'quantity':None if a.quantity is None else a.quantity*factor,'maximum':None if a.maximum is None else a.maximum*factor})
def amount_text(a):
    n = fmt(a.quantity)
    if a.maximum is not None: n += '–'+fmt(a.maximum)
    return ' '.join(x for x in (n, a.unit, a.text) if x)
def match_conversion(name, dictionary):
    name = name.lower().strip()
    return next((c for c in dictionary if name in [s.lower().strip() for s in [c['name'],*c.get('aliases',[])]]),None)
def convert(a, name, dictionary, target):
    u = unit(a.unit)
    if a.quantity is None: return None
    c = match_conversion(name,dictionary)
    multiplier = None
    dest = ''
    if target == 'metric':
        if u in WEIGHT and u not in ('g','kg'): multiplier,dest = WEIGHT[u],'g'
        elif u in VOLUME and u not in ('ml','l'):
            if c and c.get('grams_per_cup'): multiplier,dest=VOLUME[u]/240*c['grams_per_cup'],'g'
            elif c and c.get('liquid'): multiplier,dest=VOLUME[u],'ml'
    else:
        if u in WEIGHT and u in ('g','kg'):
            if c and c.get('grams_per_cup'): multiplier,dest=WEIGHT[u]/c['grams_per_cup'],'cup'
            else: multiplier,dest=WEIGHT[u]/WEIGHT['oz'],'oz'
        elif u in ('ml','l'): multiplier,dest=VOLUME[u]/240,'cup'
    if multiplier is None:return None
    return scaled(a,multiplier).model_copy(update={'unit':dest})
def display(a, ingredient, dictionary, preference='metric', factor=1):
    a = scaled(a,factor)
    eq = None
    base = ingredient.amount
    if ingredient.equivalent and base.quantity and a.quantity is not None and unit(base.unit)==unit(a.unit):
        eq=scaled(ingredient.equivalent,a.quantity/base.quantity)
        if a.maximum is not None:
            eq.maximum=ingredient.equivalent.quantity*a.maximum/base.quantity if ingredient.equivalent.quantity is not None else None
    elif ingredient.equivalent and ingredient.equivalent.quantity and a.quantity is not None and unit(ingredient.equivalent.unit)==unit(a.unit):
        eq=scaled(base,a.quantity/ingredient.equivalent.quantity)
        if a.maximum is not None: eq.maximum=base.quantity*a.maximum/ingredient.equivalent.quantity if base.quantity is not None else None
    metric = unit(a.unit) in ('g','kg','ml','l')
    if eq is None: eq=convert(a,ingredient.name,dictionary,'us' if metric else 'metric')
    first, second = a,eq
    if eq and (unit(eq.unit) in ('g','kg','ml','l')) == (preference=='metric'):
        first,second=eq,a
    values = amount_text(first)
    if second: values += ' / '+amount_text(second)
    return (values+' '+ingredient.name).strip()
def usage_amount(u,i):
    if u.mode=='amount': return u.amount
    if u.mode=='fraction': return scaled(i.amount,u.fraction)
    if u.mode=='mention': return Amount()
    return i.amount
def render(recipe, dictionary, factor=1, preference='metric'):
    lookup={i.id:i for i in recipe.ingredients}
    ingredients=[{'id':i.id,'group':i.group,'text':display(i.amount,i,dictionary,preference,factor),'preparation':i.preparation,'optional':i.optional,'alternatives':i.alternatives} for i in recipe.ingredients]
    steps=[]
    for step in recipe.steps:
        text=step.text
        for u in step.uses:
            i=lookup[u.ingredient_id]
            label = display(usage_amount(u,i),i,dictionary,preference,factor)
            if u.alternative: label += ' (or '+u.alternative+')'
            text=text.replace('{{'+u.id+'}}',label)
        steps.append({'text':text,'group':step.group})
    return {'ingredients':ingredients,'steps':steps,'factor':factor,'servings':recipe.servings*factor if recipe.servings else None}
def canonical(a):
    u=unit(a.unit)
    scale=VOLUME.get(u,WEIGHT.get(u,1))
    dim='volume' if u in VOLUME else ('weight' if u in WEIGHT else u)
    return dim, None if a.quantity is None else a.quantity*scale, None if a.quantity is None else (a.maximum if a.maximum is not None else a.quantity)*scale
def warnings(recipe):
    result=list(recipe.import_warnings)
    for n,step in enumerate(recipe.steps,1):
        unlinked=re.sub(r'\{\{[^}]+\}\}','',step.text)
        if re.search(NUM+r'\s*(?:cups?|tbsp|tsp|grams?|g|kg|ml|oz|cloves?|cans?)\b',unlinked,re.I):
            result.append(f'Step {n} contains a quantity outside an ingredient reference. It may refer to an unlisted ingredient and will not scale until linked in the editor.')
    for i in recipe.ingredients:
        uses=[u for s in recipe.steps for u in s.uses if u.ingredient_id==i.id and u.mode!='mention']
        if not uses: result.append(f'{i.name} ({i.group}) is listed but has no measured step reference.')
        if i.amount.quantity is None and not i.amount.text: result.append(f'{i.name}: quantity is unspecified; review the source.')
        dim,lo,hi=canonical(i.amount)
        vals=[canonical(usage_amount(u,i)) for u in uses]
        if vals and lo is not None:
            if any(v[0]!=dim or v[1] is None for v in vals):
                result.append(f'{i.name} ({i.group}): step quantities include an unmeasured amount or incompatible unit; review reconciliation.')
            elif abs(sum(v[1] for v in vals)-lo)>.01 or abs(sum(v[2] for v in vals)-hi)>.01:
                result.append(f'{i.name} ({i.group}): step amounts do not exactly reconcile with the ingredient total ({amount_text(i.amount)}). Source values have been preserved.')
    if not recipe.ingredients:result.append('No structured ingredients were extracted. Review and add them in the editor.')
    if not recipe.steps:result.append('No instruction steps were extracted. Review the original source.')
    return list(dict.fromkeys(result))
