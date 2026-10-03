"""Auditable, best-effort corporate-action terms. No last-quote liquidation fiction.
Economic event dates are used on or next US session; same-day receipt is an
explicit analytical assumption. Irish noncash rollover eligibility is unverified.
"""
from pathlib import Path
import csv,json
from datetime import date, timedelta
P=Path(__file__).resolve().parent
assets=json.loads((P.parent/'quantiacs_ndx_assets.json').read_text())+json.loads((P.parent/'repairs/quantiacs_general_assets.json').read_text())
ids={x['symbol']:x['id'] for x in assets}
ids.update({'CA':'tts-14011355','ALTR':'tts-130097863','LIFE':'tts-88339869','BBBY':'tts-827919','DELL':'tts-828600','DELL_NEW':'tts-157040141','SNDK':'tts-830518','CEG':'tts-239110702','PARA':'tts-240346757','FOXA_OLD':'tts-161284560','FOX_OLD':'tts-161284558','BMY':'tts-818515','AZN':'tts-203249662'})
ids.update({'DTV':'tts-12035732','GENZ':'tts-829049','SPLS':'tts-820309','FB':'tts-43902240'})
rows=[]
def add(date,symbol,kind,cash=0,new='',ratio=0,source='',notes='',status='primary_terms_verified',priority=20):
 rows.append(dict(date=date,security_id=ids.get(symbol,'yahoo:'+symbol),symbol=symbol,event_type=kind,cash_usd_per_share=cash,new_security_id=ids.get(new,'yahoo:'+new) if new else '',new_symbol=new,ratio=ratio,source=source,notes=notes,status=status,irish_tax_status='CGT_cash_disposal' if kind=='cash_merger' else 'unverified_rollover_or_basis_assumption',priority=priority))
cash_events=[
('2011-10-14','CEPH',81.5,'https://ir.tevapharm.com/news-and-events/press-releases/press-release-details/2011/Teva-Completes-Acquisition-of-Cephalon/default.aspx'),
('2013-09-10','BMC',46.25,'https://www.sec.gov/Archives/edgar/data/835729/000119312513364107/d595671d8k.htm'),
('2013-10-29','DELL',13.75,'https://www.sec.gov/Archives/edgar/data/826083/000119312513333740/d580075ddefr14a.htm'),
('2014-02-03','LIFE',76.1311786,'https://www.sec.gov/Archives/edgar/data/1073431/000119312514033495/d655804d8k.htm'),
('2015-07-23','CTRX',61.5,'https://www.sec.gov/Archives/edgar/data/1363851/000119312515261290/d23884dex991.htm'),
('2015-11-18','SIAL',140,'https://www.merckgroup.com/investors/reports-and-financials/earnings-materials/2015-q4/us/2015-Q4-Report-US.pdf'),
('2015-12-28','ALTR',54,'https://www.sec.gov/Archives/edgar/data/768251/000119312515414631/d102231d8k.htm'),
('2016-03-03','GMCR',92,'https://news.keuriggreenmountain.com/all-press-releases/press-release-details/2016/JAB-Holding-Company-Led-Investor-Group-Completes-Acquisition-of-Keurig-Green-Mountain-Inc/default.aspx'),
('2017-02-01','APOL',10,'https://www.sec.gov/Archives/edgar/data/929887/000119312517026959/d329920dex991.htm'),
('2017-04-05','JOY',28.3,'https://www.komatsu.jp/en/newsroom/2017/20170406 | https://www.komatsu.jp/ja/newsroom/2016/20160721'),
('2017-08-28','WFM',42,'https://www.sec.gov/Archives/edgar/data/1018724/000119312517269093/d448689d8k.htm'),
('2017-09-12','SPLS',10.25,'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2017-18'),
('2018-11-05','CA',44.5,'https://investors.broadcom.com/news-releases/news-release-details/broadcom-inc-completes-acquisition-ca-technologies | https://www.sec.gov/Archives/edgar/data/356028/000119312518216428/d870637d8k.htm'),
('2022-03-04','NUAN',56,'https://news.microsoft.com/source/2022/03/04/microsoft-completes-acquisition-of-nuance-ushering-in-new-era-of-outcomes-based-ai/'),
('2022-06-08','CERN',95,'https://www.oracle.com/corporate/acquisitions/cerner/'),
('2022-09-30','CTXS',104,'https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2022-262'),
('2023-10-13','ATVI',95,'https://www.sec.gov/Archives/edgar/data/789019/000119312523255762/d537928d8k.htm'),
('2023-12-14','SGEN',229,'https://www.pfizer.com/news/press-release/press-release-detail/pfizer-completes-acquisition-seagen'),
('2024-03-18','SPLK',157,'https://newsroom.cisco.com/c/r/newsroom/en/us/a/y2024/m03/cisco-completes-acquisition-of-splunk.html'),
('2024-11-04','SRCL',62,'https://investors.wm.com/news-releases/news-release-details/wm-completes-acquisition-stericycle'),
('2025-04-17','PDCO',31.35,'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2025-195'),
('2025-08-28','WBA',11.45,'https://www.sec.gov/Archives/edgar/data/1618921/000119312525190603/d87240d8k.htm'),
]
for d,s,c,u in cash_events: add(d,s,'cash_merger',cash=c,source=u,notes='Same-day cash settlement assumed. Mandatory disposal, not a voluntary rebalancing trade.'+ (' Non-transferable DAP right retained but valued at zero; contractual maximum additional $3 per old share is unresolved.' if s=='WBA' else ''))
add('2013-10-29','DELL','cash_dividend',cash=.13,source='https://www.sec.gov/Archives/edgar/data/826083/000119312513333740/d580075ddefr14a.htm',notes='Special $0.13 dividend separate from $13.75 merger consideration. Event-date cash accrual approximation; do not duplicate any vendor cash dividend.',priority=10)
add('2023-09-29','BBBY','worthless',source='https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/d579010d8k.htm',notes='Old issuer CIK886158 common stock cancelled for zero. Unquoted interval must remain untradable, not liquidated at stale price.')
add('2024-04-23','ENDP','worthless',source='https://www.sec.gov/Archives/edgar/data/2008861/000200886125000007/ndoi-20241231.htm',notes='Old Endo plc common shares cancelled under effective plan. No successor common stock for old equity. Irish loss recognition date assumed cancellation.')

# Fixed policy: elect publicly offered listed stock consideration to retain exposure
# and limit cash realization, without considering future security performance.
stock_events=[
('2013-10-01','WCRX','AGN',.16,'https://www.sec.gov/Archives/edgar/data/1578845/000119312514434971/d826386dex991.htm','AGN vendor series must be the Actavis plc lineage, not old Allergan Inc.'),
('2016-02-01','BRCM','AVGO',.4378,'https://investors.broadcom.com/news-releases/news-release-details/broadcom-limited-announces-final-broadcom-corporation-merger','Policy elects listed shares before Jan25 deadline. Stock elections were not prorated. Unverified historical broker election support.'),
('2019-12-05','VIAB','PARA',.59625,'https://ir.paramount.com/news-releases/news-release-details/viacomcbs-announces-completion-merger-cbs-and-viacom/','After-close Dec4 transaction; first successor close Dec5. VIAC later renamed PARA.'),
('2020-11-17','MYL','VTRS',1,'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2020-208','Nov16 after-close economic combination; successor begins regular trading Nov17.'),
('2021-08-26','MXIM','ADI',.63,'https://investor.analog.com/news-releases/news-release-details/analog-devices-completes-acquisition-maxim-integrated/',''),
('2022-02-14','XLNX','AMD',1.7234,'https://www.amd.com/en/newsroom/press-releases/2022-2-14-amd-completes-acquisition-of-xilinx.html',''),
('2022-04-11','DISCA','WBD',1,'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-63','Apr8 after-close merger; Apr11 regular WBD trading.'),
('2022-04-11','DISCK','WBD',1,'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2022-63','Apr8 after-close merger; Apr11 regular WBD trading.'),
('2024-01-02','DISH','SATS',.350877,'https://ir.echostar.com/news-releases/news-release-details/echostar-corporation-completes-merger-dish-network-corporation','Legal completion Dec31; first US session Jan2.'),
('2025-08-07','PARA','PSKY',1,'https://ir.paramount.com/static-files/a3510fef-59f6-4615-9a07-96387c979495','Fixed stock-election policy, no future-price selection. Listed ClassB shares, not $15 cash alternative.'),
]
for d,s,n,r,u,note in stock_events:add(d,s,'stock_exchange',new=n,ratio=r,source=u,notes=note)
mixed_events=[
('2015-07-27','DTV',28.5,'T',1.892,'https://investors.att.com/stockholder-services/cost-basis-guide/worksheet/directv','July24 close; next-session processing.'),
('2016-05-12','SNDK',67.5,'WDC',.2387,'https://www.sec.gov/Archives/edgar/data/106040/000119312516588382/d154176dex991.htm','Old SanDisk corporation only; different from2025 spin-off.'),
('2017-03-13','LLTC',46,'ADI',.2321,'https://www.sec.gov/Archives/edgar/data/6281/000115752317000729/a51520851ex99_1.htm | https://www.sec.gov/Archives/edgar/data/6281/000000628117000086/q217exhibit101.htm','March10 closing; next-session processing.'),
('2018-12-21','ESRX',48.75,'CI',.2434,'https://www.sec.gov/Archives/edgar/data/1739940/000114036118045479/form8k12b.htm','Dec20 closing; next-session processing.'),
('2019-01-08','SHPG',90.99,'TAK',5.034,'https://www.sec.gov/Archives/edgar/data/936402/000119312519004574/d673508d8k.htm','Shire ADS represented3ordinaryshares; Takeda ADS ratio units critical. Depositary fees excluded.'),
('2019-11-21','CELG',50,'BMY',1,'https://news.bms.com/news/details/2019/Bristol-Myers-Squibb-Completes-Acquisition-of-Celgene-Creating-a-Leading-Biopharma-Company/default.aspx','Also one BMYRT CVR. Retain right with zero interim mark approximation; expired2021-01-01 without payment. Separate litigation unresolved.'),
('2020-05-08','AGN',120.3,'ABBV',.866,'https://news.abbvie.com/2020-05-08-AbbVie-Completes-Transformative-Acquisition-of-Allergan',''),
('2021-05-14','FLIR',28,'TDY',.0718,'https://www.teledyne.com/en-us/news/pages/teledyne-completes-acquisition-of-flir.aspx',''),
('2021-07-21','ALXN',60,'AZN',2.1243,'https://www.astrazeneca.com/media-centre/press-releases/2021/acquisition-of-alexion-completed.html | https://www.astrazeneca.com/media-centre/press-releases/2020/astrazeneca-to-acquire-alexion.html','ADS successor represents half an ordinary share until2026conversion.'),
('2025-07-17','ANSS',197,'SNPS',.345,'https://investor.synopsys.com/news/news-details/2025/Synopsys-Completes-Acquisition-of-Ansys/default.aspx | https://ansys.synopsys.com/news-center/press-releases/1-16-24-synopsys-acquires-ansys',''),
]
for d,s,c,n,r,u,note in mixed_events:add(d,s,'mixed_merger',cash=c,new=n,ratio=r,source=u,notes=note)
add('2022-04-11','T','spinoff',new='WBD',ratio=.241917,source='https://investors.att.com/stockholder-services/cost-basis-guide/worksheet/atandt-inc-wbd',notes='Retain AT&T and WBD. Remove vendor synthetic distribution and restore pre-spin parent prices where vendor preadjusted.')


# IDs for explicit successor units absent from current Nasdaq endpoint.
ids.update({'SNDK_OLD':'tts-830518','SNDK_NEW':'tts-342851559','FB':'tts-43902240','FISV_OLD':'tts-832260'})
spin_events=[
('2011-12-21','EXPE','TRIP',1,'https://ir.tripadvisor.com/investor-faqs','Ratio is per post-reverse-split EXPE share. Apply .5 parent split FIRST; .5 TRIP per original EXPE. Remove synthetic source cash distribution.'),
('2013-07-01','FOXA_OLD','NWSA',.25,'https://www.sec.gov/Archives/edgar/data/1564708/000119312513281463/d560987dex991.htm','Retain oldNewsCorp/21CF plus newNewsCorp.'),
('2013-07-01','FOX_OLD','NWS',.25,'https://www.sec.gov/Archives/edgar/data/1564708/000119312513281463/d560987dex991.htm','ClassB sameclass entitlement.'),
('2014-03-04','LBTYA','LBTYK',1,'https://www.libertyglobal.com/investors/share-information/share-cost-basis/','ClassA retains its shares and receives one ClassC; ClassC itself doubles separately.'),
('2014-04-03','GOOGL','GOOG',1,'https://ir.nasdaq.com/node/81631','Prior priority bundle independently repaired hidden2x factor. Remove syntheticcashdividend.'),
('2014-08-07','DISCA','DISCK',1,'https://ir.corporate.discovery.com/stock-information/cost-basis-and-debt-information/series-c-dividend/default.aspx','Retain ClassA; receive oneClassC. ExistingClassC split2 separately.'),
('2014-10-01','ADP','CDK',1/3,'https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2014-78','Retain parent+child; remove fakecashdividend.'),
('2015-07-02','LBTYA','LILA',.05,'https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2015-79','Trackingstock lineage assumed continuous through2017separatecompanysameclass exchange.'),
('2015-07-02','LBTYK','LILAK',.05,'https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2015-79','Trackingstock lineage assumed continuous through2017separatecompanysameclass exchange.'),
('2015-07-20','EBAY','PYPL',1,'https://www.ebayinc.com/stories/news/ebay-inc-board-approves-completion-of-ebay-and-paypal-separation/','Prior priority bundle restored hiddenparentfactor. Remove syntheticcashdistribution38.39.'),
('2016-07-05','LBTYA','LILA',.124769,'https://www.libertyglobal.com/wp-content/uploads/2023/10/Form-8937-July-7.pdf','July1 afterclose distribution; nextsessionJuly5.'),
('2016-07-05','LBTYK','LILAK',.124769,'https://www.libertyglobal.com/wp-content/uploads/2023/10/Form-8937-July-7.pdf','July1 afterclose distribution; nextsessionJuly5.'),
('2017-02-01','CTXS','LOGM',.1718,'https://www.sec.gov/Archives/edgar/data/1420302/000119312517027557/d339688d8k.htm','Remove syntheticcashdividend18.5716; retainLOGMuntilcashmerger.'),
('2024-01-03','FLEX','NXT',.17,'https://www.sec.gov/Archives/edgar/data/866374/000086637424000005/flex-8xkexh991pr01022024pe.htm','Issuer states approximately0.17; ratio rounded approximation, not independently exact.'),
('2024-11-13','LBTYA','SUNN.SW',.2,'https://www.libertyglobal.com/investors/sunrise-spin-off/','One Sunrise ADS=one Swissordinary. NASDAQ temporary listing; subsequent Swissprice conversion needed.'),
('2024-11-13','LBTYK','SUNN.SW',.2,'https://www.libertyglobal.com/investors/sunrise-spin-off/','One Sunrise ADS=one Swissordinary. NASDAQ temporary listing; subsequent Swissprice conversion needed.'),
('2025-02-24','WDC','SNDK_NEW',1/3,'https://investor.sandisk.com/static-files/04748788-0649-42cf-840f-3cd4502bb85a','NewSandisk CIK2023554; notold2016acquiredissuer.'),
]
for d,s,n,r,u,note in spin_events:add(d,s,'spinoff',new=n,ratio=r,source=u,notes=note,priority=15)
# These must override any vendor synthetic split, not duplicate it.
for d,s,r,u,note in [
('2011-12-21','EXPE',.5,'https://ir.tripadvisor.com/investor-faqs','Reverse split immediately before TripAdvisor reclassification.'),
('2014-03-04','LBTYK',2,'https://www.libertyglobal.com/investors/share-information/share-cost-basis/','One extra sameclassshare per originalClassC.'),
('2014-08-07','DISCK',2,'https://ir.corporate.discovery.com/stock-information/cost-basis-and-debt-information/series-c-dividend/default.aspx','One extra sameclassshare per originalClassC. Process before DISCA adds newCshares.'),
('2015-04-27','GOOG',1.0027455,'https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2015-52','ClassC adjustment retained asfractionalstock; actualcash-in-lieu excluded.'),
('2026-02-02','AZN',.5,'https://www.sec.gov/Archives/edgar/data/901832/000165495426000464/a4875p.htm','TwoADSs becomeoneordinaryshare.')]:add(d,s,'split',new=s,ratio=r,source=u,notes=note,priority=5)
add('2020-08-31','LOGM','cash_merger',cash=86.05,source='https://www.sec.gov/Archives/edgar/data/1420302/000119312520235656/d137287dex991.htm')
add('2022-07-06','CDK','cash_merger',cash=54.87,source='https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2022-164')
for old,new in [('FOXA_OLD','FOXA'),('FOX_OLD','FOX')]:
 add('2019-03-19',old,'split',new=old,ratio=.736817,source='https://thewaltdisneycompany.com/press-releases/21st-century-fox-and-disney-announce-distribution-adjustment-multiple-in-connection-with-acquisition-and-effect-on-outstanding-shares/',notes='Share shrink in separation; process before spin allocation.',priority=5)
 add('2019-03-19',old,'spinoff',new=new,ratio=(1/3)/.736817,source='https://thewaltdisneycompany.com/press-releases/21st-century-fox-and-disney-announce-distribution-adjustment-multiple-in-connection-with-acquisition-and-effect-on-outstanding-shares/',notes='1/3 newFox peroriginaloldshare. Expressed per .736817oldsharepostshrink.',priority=15)
 add('2019-03-20',old,'stock_exchange',new='DIS',ratio=.4517,source='https://www.sec.gov/Archives/edgar/data/1744489/000095015719000301/form8k-12b.htm',notes='Fixedlisted-stock election; stock/noelection notprorated. Ratio peroldshare afterMar19shrink.')
add('2015-01-20','FWLT','mixed_merger',cash=16,new='AMFW',ratio=.8998,source='https://www.sec.gov/Archives/edgar/data/1328798/000093041316006120/c84401_20f.htm | https://www.sec.gov/Archives/edgar/data/1130385/000110465914080103/a14-20247_6sc14d9a.htm',notes='No voluntary tender: Jan19 squeezeout, nextUSsessionJan20. Same baseofferterms assumed; actualcash/shareelectionproration unverified.',status='terms_verified_base_mix_approximation')
add('2017-10-09','AMFW','stock_exchange',new='WG.L',ratio=.75,source='https://www.woodgroup.com/news/wood-group-completes-acquisition-of-amec-foster-wheeler | https://www.ice.com/publicdocs/liffe/corporate_actions/2017/CA-2017-639-Lo.pdf',notes='Wood ordinaryshares priced inGBP(pencequotesdivide100). ADS1:1 assumed; actualdepositarytransitionunverified.')
# Pure symbol changes can be implemented as aliases rather than transactions.
add('2022-11-08','NLOK','symbol_change',new='GEN',ratio=1,source='https://investor.gendigital.com/news/news-details/2022/Introducing-Gen-The-Company-to-Power-Digital-Freedom/default.aspx/1000/default.aspx',notes='Sameissuer CIK849399, no disposal.')
add('2022-06-09','FB','symbol_change',new='META',ratio=1,source='https://investor.atmeta.com/investor-news/press-release-details/2022/Meta-Platforms-Inc.-to-Change-Ticker-Symbol-to-META-on-June-9/default.aspx',notes='Sameissuer CUSIP30303M102. Oldvendor endsDec2021 incorrectly; aliasprices bridgegap.')
add('2023-06-07','FISV_OLD','symbol_change',new='FI',ratio=1,source='https://investors.fiserv.com/news-releases/news-release-details/fiserv-completes-listing-transfer-new-york-stock-exchange',notes='Sameissuer; laterFISVreturn notdisposal.')


add('2011-04-11','GENZ','cash_merger',cash=74,source='https://echanges.dila.gouv.fr/OPENDATA/AMF/ECO/2011/04/FCECO020209_20110408.pdf',notes='April 8 after-close merger. One GCVRZ right tracked separately with zero interim analytical mark and approximately $0.89 settlement in March 2020.',status='cash_verified_CVR_payout_approximation')

# New terms appended below.
add('2013-06-07','VMED','spinoff',new='LBTYK',ratio=.1928,source='https://www.sec.gov/Archives/edgar/data/1270400/000127040013000106/vmed-6302013xq2.htm',notes='First leg of one mandatory multi-class merger. Basis must be apportioned using combined $17.50 cash plus .2582 LBTYA plus .1928 LBTYK value, not an extinct parent quote.',priority=15)
add('2013-06-07','VMED','mixed_merger',cash=17.5,new='LBTYA',ratio=.2582,source='https://www.virginmedia.com/corporate/investors-overview',notes='Second leg of same multi-class merger; cancel all old VMED shares. Contemporaneous class C ratio .1928, not later split-adjusted .6438.')

extra_spins=[
('2011-11-22','MAR','VAC',.1,'https://marriott.gcs-web.com/news-releases/news-release-details/marriott-international-board-approves-spin-marriott-vacations','November 21 after-close distribution; first ex-date November 22.'),
('2015-08-04','VIAV','LITE',.2,'https://www.sec.gov/Archives/edgar/data/1633978/000119312515251781/d870553dex991.htm','JDSU renamed VIAVI; retain one parent share and receive 1/5 Lumentum. Vendor synthetic split is not extra parent shares.'),
('2016-10-03','HON','ASIX',.04,'https://investor.honeywell.com/news-releases/news-release-details/honeywell-board-directors-declares-spin-dividend-advansix-shares','October 1 legal completion; first US session October 3.'),
('2018-10-01','HON','GTX',.1,'https://www.sec.gov/Archives/edgar/data/773840/000077384020000009/R8.htm','Retain Honeywell and Garrett; Garrett later bankruptcy requires separate treatment if held.'),
('2018-10-29','HON','REZI',1/6,'https://www.sec.gov/Archives/edgar/data/773840/000119312518309906/d646107d8k.htm','Retain Honeywell and one Resideo for six shares.'),
('2019-02-08','HSIC','CVET',.4,'https://investor.henryschein.com/news-releases/news-release-details/2019/Henry-Schein-Announces-New-Distribution-Date-And-Anticipated-When-Issued-Trading-Market-For-Spin-Off-Of-Animal-Health-Business-01-16-2019/default.aspx','February 7 after-close distribution; Covetrus trades regular way February 8.'),
('2021-11-02','DELL_NEW','VMW',.440626,'https://www.sec.gov/Archives/edgar/data/1571996/000119312521315488/d146470d8k.htm','November 1 distribution, ex-date November 2. New Dell Technologies, not old Dell acquired in 2013.'),
('2022-02-02','EXC','CEG',1/3,'https://www.exeloncorp.com/newsroom/exelon-completes-separation-of-constellation','Retain Exelon and Constellation Energy.'),
('2024-06-25','ILMN','GRAL',1/6,'https://www.sec.gov/Archives/edgar/data/1110803/000119312524167025/d851030d8k.htm','June 24 completion, June 25 first regular session and parent ex-date.'),
]
for d,s,n,r,u,note in extra_spins:add(d,s,'spinoff',new=n,ratio=r,source=u,notes=note,priority=15)
add('2022-10-13','CVET','cash_merger',cash=21,source='https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2022-284 | https://covetrus.com/newsroom/covetrus-to-be-acquired-by-clayton-dubilier-rice-and-tpg-at-an-enterprise-valuation-of-approximately-4-billion/')
add('2023-11-22','VMW','mixed_merger',cash=142.5*.479,new='AVGO',ratio=.252*.521,source='https://www.broadcom.com/company/news/financial-releases/61501 | https://investors.broadcom.com/news-releases/news-release-details/broadcom-completes-acquisition-vmware',notes='Policy elects stock before October 23 deadline; issuer reports approximately 52.1% stock and 47.9% cash proration for stock elections. Rounded proration approximation; fractional cash-in-lieu excluded.',status='primary_terms_verified_rounded_proration')
for old in ['FWONA','FWONK']:
 add('2023-07-20',old,'spinoff',new='BATRK',ratio=.028960604,source='https://www.libertymedia.com/investors/news-events/press-releases/detail/503/liberty-media-corporation-announces-completion-of',notes='Both Formula One classes receive Braves Series C. July 19 after-close distribution; exact final ratio replaces provisional announcement.',priority=15)
for old,new,r in [('FWONA','LLYVA',.0428),('FWONK','LLYVK',.0428),('LSXMA','LLYVA',.25),('LSXMK','LLYVK',.25)]:
 add('2023-08-04',old,'spinoff',new=new,ratio=r,source='https://www.libertymedia.com/investors/stock-data/faq',notes='August 3 after-close tracking-stock reclassification. Retain parent; Liberty Live tracking-stock continuity later requires current listing verification.',priority=15)
for d,s,n,r,u in [
('2025-10-30','HON','SOLS',.25,'https://www.honeywell.com/us/en/news/press-releases/2025/10/honeywell-completes-spin-off-of-solstice-advanced-materials'),
('2026-01-05','CMCSA','VSNT',.04,'https://www.cmcsa.com/node/44806'),
('2026-06-29','HON','HONA',1,'https://www.sec.gov/Archives/edgar/data/773840/000077384026000124/hon-20260630.htm')]:add(d,s,'spinoff',new=n,ratio=r,source=u,notes='Retain parent and listed successor shares. Remove corresponding vendor synthetic cash distribution or split.'+(' HONA ratio is per POST 1-for-2 consolidated HON share: equivalent to .5 HONA per original HON.' if n=='HONA' else ''),priority=15)
add('2026-06-29','HON','split',new='HON',ratio=.5,source='https://www.honeywell.com/us/en/press/2026/06/honeywell-board-of-directors-sets-record-date-and-announces-expected-timing-for-spin-off-of-honeywell-aerospace-and-honeywell-reverse-stock-split',notes='Mandatory 1-for-2 parent consolidation. Legally follows distribution; computationally applied first with HONA entitlement scaled to one per consolidated HON.',priority=5)
add('2026-04-07','HOLX','cash_merger',cash=76,source='https://www.hologic.com/about/press-release/blackstone-and-tpg-complete-acquisition-hologic',notes='Also retain one non-tradable CVR, marked zero provisionally. Maximum additional $3 in two up-to-$1.50 payments tied to FY2026 and FY2027 Breast Health revenue; not asserted worthless.',status='cash_verified_CVR_unpriced')
add('2026-08-04','EA','cash_merger',cash=210,source='https://careers.ea.com/playtesting/news/ea-announces-completion-of-acquisition',notes='Issuer confirms completion August 4, 2026. Event-date cash settlement assumed.')
add('2016-12-09','STRZA','mixed_merger',cash=18,new='LGF-B',ratio=.6784,source='https://www.sec.gov/Archives/edgar/data/929351/000157104916020445/t1602966_ex99-1.htm',notes='December 8 close, December 9 first new-class regular trading. Starz Series A receives only Lionsgate class B, not both classes.')
add('2025-02-24','QRTEA','symbol_change',new='QVCGA',ratio=1,source='https://www.qvcgrp.com/newsroom/pressrelease/qurate-retail-officially-becomes-qvc-group/',notes='Same issuer, not a cash disposal. Subsequent reverse split and bankruptcy need separate treatment.')
add('2025-05-23','QVCGA','split',new='QVCGA',ratio=.02,source='https://investors.qvcgrp.com/news-media/press-releases/detail/656/qvc-group-inc-announces-reverse-stock-split-intention-to',notes='May 22 legal effective time after market close; May 23 split-adjusted trading. Fractional shares retained analytically.',priority=5)

# Side-pocket contingent entitlements. No trading, future-price-informed decisions,
# or claims that a zero analytical mark means the claim is economically worthless.
ids.update({'GENZ_CVR':'right:GENZ_CVR','WBA_DAP':'right:WBA_DAP','HOLX_CVR':'right:HOLX_CVR','CELG_CVR':'right:CELG_CVR'})
for d,s,n,u,note in [
('2011-04-11','GENZ','GENZ_CVR','https://echanges.dila.gouv.fr/OPENDATA/AMF/ECO/2011/04/FCECO020209_20110408.pdf','One GCVRZ per original share. No voluntary trading modelled; zero interim value and zero allocated basis are approximations. Original conditional maximum $14.'),
('2019-11-21','CELG','CELG_CVR','https://news.bms.com/news/details/2019/Bristol-Myers-Squibb-Completes-Acquisition-of-Celgene-Creating-a-Leading-Biopharma-Company/default.aspx','One transferable CVR, conditional maximum $9; contract expired without payment in January 2021, subsequent litigation is a separate unresolved claim.'),
('2025-08-28','WBA','WBA_DAP','https://www.sec.gov/Archives/edgar/data/1618921/000119312525190603/d87240d8k.htm','One non-transferable DAP right, maximum future proceeds $3; no payout verified through analysis endpoint. Zero valuation is an approximation.'),
('2026-04-07','HOLX','HOLX_CVR','https://www.hologic.com/about/press-release/blackstone-and-tpg-complete-acquisition-hologic','One non-transferable CVR, maximum $3 across two up-to-$1.50 revenue-contingent payments. Zero valuation is an approximation.')]:add(d,s,'contingent_right',new=n,ratio=1,source=u,notes=note,status='primary_entitlement_verified_interim_value_approximation',priority=5)
add('2020-03-05','GENZ_CVR','contingent_cash',cash=.89,source='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2020-40',notes='Exchange gives approximately $0.89 per CVR. Actual broker receipt date and exact net distribution unverified; suspension date used as cash date. Treating receipt as CGT proceeds with zero right basis is provisional.',status='exchange_reported_approximate_amount_and_timing')
for s in ['LSXMA','LSXMK']:
 add('2024-09-10',s,'stock_exchange',new='SIRI',ratio=.8375,source='https://www.libertymedia.com/investors/financial-information/sec-filings/content/0001225208-24-008597/0001225208-24-008597.pdf',notes='September 9 after-close exchange. Ratio is in new Sirius shares after old SIRI .1 consolidation; process old SIRI split before issuing new shares.')
for s,r in [('LGF-A',1.12),('LGF-B',1)]:
 add('2025-05-07',s,'spinoff',new='STRZ',ratio=r/15,source='https://www.sec.gov/Archives/edgar/data/929351/000092935126000022/starz2025transitionannualr.pdf',notes='First leg of mandatory two-child separation. Combined basis must use post-separation LION and STRZ values, not stale extinct LGF quote; ratio includes new Starz 1-for-15 consolidation.',priority=15)
 add('2025-05-07',s,'stock_exchange',new='LION',ratio=r,source='https://www.sec.gov/Archives/edgar/data/929351/000092935126000022/starz2025transitionannualr.pdf',notes='Second leg, cancels old LGF class. May 6 completion; first regular trading May 7.')
add('2019-10-02','NUAN','spinoff',new='CRNC',ratio=.125,source='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2019-178',notes='One Cerence for eight Nuance shares; retain parent. Parent hidden spin factor must be removed from raw prices.',priority=15)
add('2026-08-06','QVCGA','worthless',source='https://www.sec.gov/Archives/edgar/data/1254699/000110465926107125/tm2625133-1_s1.htm',notes='Old QVC common and preferred legally cancelled for no consideration. New QVCG common belongs to creditors; no share continuity. QVCGA/QVCAQ treated as one old security.')
add('2021-01-04','CELG_CVR','contingent_cash',cash=0,source='https://news.bms.com/news/details/2021/Bristol-Myers-Squibb-Provides-Update-on-Status-of-Contingent-Value-Rights/default.aspx',notes='Agreement terminated January 1, 2021 with no payment; first US session January 4. Separate litigation claim unresolved; do not assume legal release of litigation rights.')
for d,c,r,u in [
('2017-01-25',1.04,26/27,'https://www.nasdaqtrader.com/TraderNews.aspx?id=ETA2017-17'),
('2024-01-30',1.28,.97,'https://corporate.qiagen.com/English/newsroom/press-releases/press-release-details/2024/QIAGEN-announces-details-for-completion-of-synthetic-share-repurchase-of-up-to-approximately-300-million/'),
('2025-01-29',1.26,35/36,'https://corporate.qiagen.com/English/newsroom/press-releases/press-release-details/2025/QIAGEN-announces-adjustment-of-conversion-price-under-its--US-500000000-Convertible-Bonds-due-2031/default.aspx'),
('2026-01-08',2.29,.95,'https://corporate.qiagen.com/English/newsroom/press-releases/press-release-details/2026/QIAGEN-announces-adjustment-of-conversion-price-under-its-US-500000000-Convertible-Bonds-due-2027/default.aspx')]:
 add(d,'QGEN','split',new='QGEN',ratio=r,source=u,notes='Mandatory synthetic repurchase consolidation. Must override vendor split and not duplicate it.',priority=5)
 add(d,'QGEN','cash_dividend',cash=c/r,source=u,notes=f'Issuer capital repayment ${c} per PRE-consolidation share; ledger amount is per POST-consolidation share. Capital-versus-income Irish classification unverified; dividend-rate taxation is a provisional conservative assumption. Cash accrued on ex-date; suppress vendor duplicate.',status='economic_terms_verified_Irish_capital_return_classification_unverified',priority=10)
vod_source='https://nasdaqtrader.com/TraderNews.aspx?id=ETA2014-14'
add('2014-02-24','VOD','split',new='VOD',ratio=6/11,source=vod_source,notes='Mandatory ADR consolidation. Apply before post-consolidation-unit cash and Verizon entitlement below.',priority=5)
add('2014-02-24','VOD','cash_dividend',cash=4.928005/(6/11),source=vod_source,notes='Cash entitlement $4.928005 per OLD ADR, expressed per consolidated ADR after split. Actual payable date March 4; ex-date accrual approximation. UK scheme/ADR and Irish tax classification unverified.',priority=10)
add('2014-02-24','VOD','spinoff',new='VZ',ratio=.263001/(6/11),source=vod_source,notes='Verizon entitlement .263001 shares per OLD Vodafone ADR, expressed after 6/11 parent consolidation. Irish taxation of stock distribution versus rollover unverified; no automatic inference from UK or US tax treatment.',priority=15)
add('2012-10-02','MDLZ','spinoff',new='KRFT',ratio=1/3,source='https://www.sec.gov/Archives/edgar/data/1103982/000119312512411522/d418430d8k.htm',notes='Old Kraft Foods/KFT changed name to Mondelez and retained same parent CIK1103982. October 1 after-close spin, October 2 ex-date. KRFT CIK1545158 is separate; do not use present KHC series as its historical daily prices.',priority=15)
kraft_merger_source='https://www.sec.gov/Archives/edgar/data/1545158/000119312515244355/d36612d8k.htm'
add('2015-07-06','KRFT','cash_dividend',cash=16.5,source=kraft_merger_source,notes='SEC legal terms classify $16.50 as a separately declared special dividend to premerger holders, not cash stock-exchange consideration. Ex-date settlement accrual approximation; suppress any vendor duplicate.',priority=10)
add('2015-07-06','KRFT','stock_exchange',new='KHC',ratio=1,source=kraft_merger_source,notes='July 2 completion, first regular KHC trading July 6. Special dividend is separate row.')
add('2020-09-15','QRTEA','spinoff',new='QRTEP',ratio=.03,source='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2020-154',notes='Preferred share dividend, regular trading September 15. Parent $1.50 cash distribution is retained from vendor. Preferred par/liquidation preference $100 is only a valuation proxy if historical quotes cannot be recovered. Irish issue-date income/CGT basis treatment unverified.',status='entitlement_verified_price_and_Irish_tax_approximation',priority=15)
qurate_div_source='https://www.sec.gov/Archives/edgar/data/1355096/000110465924052082/tm242657d4_ars.pdf | https://investors.qvcgrp.com/investors/sec-filings/post-split-liberty-interactive/xbrl_doc_only/9606'
for year in range(2020,2026):
 for month in (3,6,9,12):
  if (year,month)<(2020,12) or (year,month)>(2025,3):continue
  paid=date(year,month,15)
  while paid.weekday()>=5:paid+=timedelta(days=1)
  add(paid.isoformat(),'QRTEP','cash_dividend',cash=2,source=qurate_div_source,notes='Documented quarterly preferred cash dividend schedule through March 2025; payable-date recognition. Weekend shifted to Monday, other settlement differences ignored. December 2020 first stub is rounded to $2.00. No dividend paid from June 2025 after suspension.',status='quarterly_cash_verified_first_stub_and_payment_timing_approximation',priority=10)
add('2026-08-06','QRTEP','worthless',source='https://www.sec.gov/Archives/edgar/data/1254699/000110465926107125/tm2625133-1_s1.htm',notes='Same old preferred security later QVCGP/QVCPQ. All old common and preferred cancelled for no recovery. Accrued unpaid dividends never treated as cash received.')
add('2026-03-10','WG.L','cash_merger',source='https://www.investegate.co.uk/announcement/rns/wood-group-john---wg./scheme-effective/9466612 | https://www.woodgroup.com/news/court-sanction-of-scheme-of-arrangement | https://www.woodplc.com/investors/pages/sidara-proposal-2025/?a=311259',notes='Mandatory scheme: 30 PENCE cash per UK ordinary share = GBP0.30, not USD0.30. Convert cash_native_per_share by event-date GBPUSD. Settlement date approximation.')
rows[-1].update(cash_currency='GBP',cash_native_per_share=.30)
add('2020-09-15','QRTEA','cash_dividend',cash=1.5,source='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2020-154',notes='Real cash component alongside .03 preferred share dividend. Explicit row must replace, not duplicate, vendor $1.50. Ex-date accrual.',priority=10)
add('2021-11-12','QRTEA','cash_dividend',cash=1.25,source='https://investors.qvcgrp.com/investors/sec-filings/post-split-liberty-interactive/content/0001355096-21-000042/0001355096-21-000042.pdf',notes='Special common dividend missing in original vendor panel. November 12 ex-date; November 22 payment. Replace any vendor duplicate.',priority=10)

# Continued holdings require later corporate actions even after index deletion.
# ECHO and SATS are the same issuer/CUSIP. The price panel keeps canonical SATS ID;
# processors must treat this same-ID symbol_change as a no-op on lots and basis.
add('2026-06-24','SATS','symbol_change',new='SATS',ratio=1,source='https://ir.echostar.com/news-releases/news-release-details/echostar-changing-stocker-ticker-sats-echo-marking-companys-next',notes='Ticker SATS becomes ECHO with unchanged CUSIP. Canonical ID remains tts-12361625; same-ID event must not remove or duplicate lots. No tax disposal.')
rows[-1]['new_symbol']='ECHO'
for parent,child in [('LBRDA','GLIBA'),('LBRDK','GLIBK')]:
 add('2025-07-15',parent,'spinoff',new=child,ratio=.2,source='https://www.libertycapitalcorp.com/investors/financial-information/sec-filings/content/0001104659-25-067808/tm2519293d4_8-k.htm',notes='July14 after-close distribution; July15 regular trading. New 2025 GCI Liberty CIK2057463, not old GCI Liberty sharing the ticker. May21 2026 name change to Liberty Capital preserves security and CUSIP. Remove vendor synthetic quantity split or cash distribution.',priority=15)
 add('2026-08-20',parent,'stock_exchange',new='CHTR',ratio=.236,source='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-577 | https://corporate.charter.com/newsroom/charter-and-cox-communications-complete-transaction',notes='Mandatory all-stock merger; last trading August19, announced closing August20, suspension August21. Same-day successor receipt assumption.')
for parent in ['LILA','LILAK']:
 add('2026-06-17',parent,'spinoff',new='LILAP',ratio=.1,source='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-363 | https://www.sec.gov/Archives/edgar/data/1712184/000171218426000087/exhibit991pressreleasedate.htm',notes='One 9% SeriesA preference share per10common, $25 liquidation preference. Ex-date June17. Vendor1.472 price-adjustment factor is NOT a common-share quantity split. Preferred dividends handled by its own cash history. Irish stock-distribution income treatment unverified.',priority=15)

def write():
 fields=['date','security_id','symbol','event_type','cash_usd_per_share','new_security_id','new_symbol','ratio','source','notes','status','irish_tax_status','priority','cash_currency','cash_native_per_share']
 with (P/'actions.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(sorted(rows,key=lambda x:(x['date'],x['priority'],x['symbol'])))
 (P/'actions_methodology.json').write_text(json.dumps({'scope':'Best-effort public corporate-action reconstruction; primary economic terms separated from unverified Irish tax treatment.','event_count':len(rows),'economic_units':'Contemporaneous unadjusted shares; do not apply these ratios to already split-adjusted price units.','cash_settlement':'Event date or next US session, an approximation.','fractional_shares':'Retained analytically, ignoring broker cash-in-lieu and minimum holding rules.','spinoff_tax':'FMV cost-basis allocation with provisional rollover assumption; a US tax-free statement is not Irish tax advice.','mandatory_disposals':'Cash takeovers and legal cancellations occur even though voluntary profitable sales are prohibited.','unknown_rights':'Explicit zero mark approximation requires exposure disclosure; not asserted worthless unless legal expiry verified.'},indent=2)+'\n')
 review=[]
 special={
  'tts-367344332':('wrong_issuer','Current BBBY is former Overstock CIK1130713, not old Bed Bath & Beyond CIK886158. Do not use this history for old index membership.'),
  'tts-181976270':('vendor_terminal_gap','SMCI quote cutoff is not evidence of a disposal. Continue same issuer with alternate quotes.'),
  'tts-818716':('ambiguous_vendor_identity','2022 Constellation spin is CIK1868275/native tts-239110702; old vendor name/ID must not override identity.'),
 }
 with (P.parent/'required_terminal_price_gaps_review.csv').open() as f:
  for item in csv.DictReader(f):
   matched=[x for x in rows if x['security_id']==item['id']]
   terminal=[x for x in matched if x['event_type'] in {'cash_merger','mixed_merger','stock_exchange','symbol_change','worthless'}]
   if item['id'] in special:classification,note=special[item['id']]
   elif terminal:classification,note='explicit_event_terms','Economic terminal/symbol-change event recorded. This does not validate preceding daily quotes, broker availability, or Irish tax treatment.'
   else:classification,note='unresolved_no_fictional_sale','No forced disposal assumed from vendor quote cutoff; obtain continued quotes or actual legal-event evidence.'
   review.append(dict(security_id=item['id'],symbol=item['symbol'],vendor_last_price=item['last_price'],classification=classification,event_dates=' | '.join(x['date'] for x in terminal),event_types=' | '.join(x['event_type'] for x in terminal),sources=' | '.join(x['source'] for x in terminal),notes=note))
 with (P/'actions_terminal_coverage.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(review[0]));writer.writeheader();writer.writerows(review)
 unresolved=[
  ('Irish corporate-action taxation','Economic terms verified where cited; Irish rollover, capital-return, foreign stock dividend, preference issuance, and contingent-right taxation remain provisional.'),
  ('Unavailable child daily prices','CDK, LOGM, KRFT, AMFW, WG.L, LGF-B, and QRTEP require alternate histories or explicitly disclosed non-tradable frozen marks. The economic ledger must not imply these quotes exist.'),
  ('Interim rights prices','GCVRZ and BMYRT were historically tradable but no voluntary rights trades are modelled. Zero interim marks and zero allocated basis are assumptions, not observed prices.'),
  ('Outstanding contingent proceeds','WBA DAP and HOLX CVR have contractual maxima of $3 per original share each. No future payment is assumed. BMY CVR expired contractually; separate litigation outcome not independently resolved.'),
  ('Rounded ratios and dates','FLEX NXT .17, VMW election proration .521/.479, first QRTEP quarterly coupon $2, GENZ CVR $.89, and same-day settlement are identified approximations.'),
  ('Fixed stock-election policy','Where offered, select listed stock before known election deadline without reference to future returns. Actual historical Trading212 election facilities are unverified.'),
  ('Other rights and foreign events','LILA/LILAK rights issues and several foreign return-of-capital mechanisms remain only vendor actions unless explicitly listed. Do not label all corporate actions comprehensive or tax-validated.'),
 ]
 with (P/'actions_unresolved.csv').open('w',newline='') as f:
  writer=csv.writer(f);writer.writerow(['topic','limitation']);writer.writerows(unresolved)
if __name__=='__main__':write();print(len(rows),'events')
