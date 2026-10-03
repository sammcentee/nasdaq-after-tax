from pathlib import Path
import pandas as pd,numpy as np,xarray as xr,json
P=Path(__file__).parent
A=xr.open_dataarray(P/'quantiacs_ndx_all.nc',engine='scipy')
M={a['id']:a for a in json.loads((P/'quantiacs_ndx_assets.json').read_text())}
close=A.sel(field='close').to_pandas();divs=A.sel(field='divs').to_pandas();split=A.sel(field='split_cumprod').to_pandas()
prior=close.shift(1);ratio=divs/prior
flags=[]
for dt,i in zip(*np.where((ratio>0.03).values)):
 date=ratio.index[dt];asset=ratio.columns[i];flags.append({**M[asset],'date':str(date.date()),'prior_close':prior.loc[date,asset],'close':close.loc[date,asset],'divs':divs.loc[date,asset],'dividend_to_prior_close':ratio.loc[date,asset],'price_return':close.loc[date,asset]/prior.loc[date,asset]-1,'naive_total_return':(close.loc[date,asset]+divs.loc[date,asset])/prior.loc[date,asset]-1,'review_status':'unreviewed; may be legitimate special cash dividend, spin distribution, or data error'})
pd.DataFrame(flags).to_csv(P/'large_distribution_review.csv',index=False)
flags=[]
r=(close+divs.fillna(0))/prior-1
for dt,i in zip(*np.where(((r>0.5)|(r<-.5)).values)):
 date=r.index[dt];asset=r.columns[i];flags.append({**M[asset],'date':str(date.date()),'prior_close':prior.loc[date,asset],'close':close.loc[date,asset],'divs':divs.loc[date,asset],'naive_total_return':r.loc[date,asset],'split_cumprod':split.loc[date,asset]})
pd.DataFrame(flags).to_csv(P/'extreme_daily_return_review.csv',index=False)
print('Large distributions',len(pd.read_csv(P/'large_distribution_review.csv')))
print('Extreme daily returns',len(flags))
print(pd.read_csv(P/'large_distribution_review.csv')[['symbol','id','date','divs','dividend_to_prior_close','price_return']].to_string(index=False))
