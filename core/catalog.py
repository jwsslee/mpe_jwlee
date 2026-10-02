"""Restored research reference, separate from automatically collected prices."""
from pathlib import Path
import pandas as pd


def catalog():
    frame=pd.read_csv(Path(__file__).resolve().parents[1]/'data/companies.csv',dtype=str).fillna('')
    def stage(row):
        if row['code'] in ('039030','039440'):return '전·후공정'
        if '테스트' in row['process']:return '후공정 · 테스트'
        if any(term in row['process'] for term in ('패키징','접합','범핑','적층')):return '후공정 · 패키징'
        if '공정 지원' in row['process']:return '공통 · 지원'
        return '전공정'
    frame['stage']=frame.apply(stage,axis=1)
    return frame[['name','code','market','stage','process','category','group','business','products']]


def filter_catalog(frame,query='',stage='전체',category='전체',product='전체',group='전체'):
    result=frame.copy()
    if query.strip():
        text=result[['name','code','business','group','process']].agg(' '.join,axis=1)
        result=result[text.str.contains(query.strip(),case=False,regex=False)]
    for column,value in [('stage',stage),('group',group)]:
        if value!='전체':result=result[result[column]==value]
    if category!='전체':result=result[result.category.str.split('·').apply(lambda xs:category in xs)]
    if product!='전체':result=result[result.products.str.split('|').apply(lambda xs:product in xs)]
    return result
