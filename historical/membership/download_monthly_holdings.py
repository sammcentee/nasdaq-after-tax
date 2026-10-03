"""Download public dated CNDX holdings; rejects missing/date-substituted results."""
import calendar,concurrent.futures,csv,datetime,json,pathlib,time
import requests
BASE='https://www.blackrock.com/varnish-api/uk-retail01-product-data/product-data/api/v2/get-product-data'
PARAMS=dict(appSubType='ISHARES',appType='PRODUCT_PAGE',component='holdings.all',locale='en_GB',portfolioId='253741',targetSite='ishares-uk',userType='individual',excludeContent='true',includeConfig='true')
DIR=pathlib.Path(__file__).parent

def get(d):
 path=DIR/'ishares_archive'/f'{d}.json'
 for attempt in range(3):
  try:
   if path.exists(): x=json.loads(path.read_text())
   else:
    r=requests.get(BASE,params={**PARAMS,'asOfDate':d},timeout=20);r.raise_for_status();x=r.json();path.write_text(json.dumps(x))
   p=x['componentsByNameMap']['holdings']['containersByNameMap']['all']['dataPointsByNameMap']
   actual=p['asOfDate']['value']; tick=p['ticker']['value']
   if str(actual)!=d or not isinstance(tick,list): return [],dict(requested=d,returned=actual,status='missing_or_wrong_date',rows=0)
   fields=['ticker','issueName','holdingPercent','marketValue','isin','assetClass','marketCurrencyCode','unitsHeld','unitPrice','exchange','sectorName']
   arrays={k:p.get(k,{}).get('value') for k in fields}
   rows=[dict(date=d,**{k:(v[i] if isinstance(v,list) and len(v)>i else None) for k,v in arrays.items()}) for i in range(len(tick))]
   return rows,dict(requested=d,returned=actual,status='valid',rows=len(rows))
  except Exception as e:
   if attempt==2:return [],dict(requested=d,returned='',status=str(e),rows=0)
   time.sleep(.5)

def main():
 dates=[]
 for y in range(2010,2027):
  for m in range(1,13):
   if (y,m)<(2010,9) or (y,m)>(2026,9):continue
   d=datetime.date(y,m,calendar.monthrange(y,m)[1])
   while d.weekday()>4:d-=datetime.timedelta(days=1)
   dates.append(d.strftime('%Y%m%d'))
 rows=[];audit=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as p:
  for batch,info in p.map(get,dates):
   rows.extend(batch);audit.append(info)
   print(info,flush=True)
 for filename,data in [('cndx_monthly_holdings.csv',rows),('cndx_archive_audit.csv',audit)]:
  with (DIR/filename).open('w') as f:
   w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
 print('saved',len(rows),'holdings',sum(a['status']=='valid' for a in audit),'snapshots',flush=True)
if __name__=='__main__':main()
