# -*- coding: utf-8 -*-
"""
Created on Sun Jan 24 12:37:24 2021

@author: aruna
"""

# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""
from flask import Flask, jsonify, render_template, request, redirect, url_for
import pandas as pd
import numpy as np
import datetime
import selenium
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait as wdw
from selenium.webdriver.common.by import By as by
from selenium.webdriver.support import expected_conditions as ec
from pandas.tseries.offsets import BDay
import time
from selenium.webdriver.support.ui import Select
import os
import sys

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!!'
app.debug = True

@app.route("/")
@app.route("/sendetails", methods=['GET','POST'])
def home():
    
    if request.method == 'POST':
        print("-- got POST --")
        
        sdatestr =  request.form['sdt']
        edatestr =  request.form['edt']
        stockcode =  request.form['stock']
        
        thresh = request.form['threshold']
            
        errors = []
        sdate = datetime.datetime.strptime(sdatestr,'%Y-%m-%d')
        edate = datetime.datetime.strptime(edatestr, '%Y-%m-%d')
        
        if sdate > edate:
            errors.append("Startdate is after the end date")
            
        if len(stockcode) != 5:
            errors.append("Stock code needs to be 5 characters: Pad zeroes")
            
        if thresh != "":
            try: 
                thresh = float(thresh)
            except:
                errors.append("Invalid Price.")
        if errors:
            return('The following errors have occured' + str(errors))
        
        if request.form['submit_button'] == 'Thresh':
            
            threshhold = thresholdchange(stockcode,sdate,edate,thresh)
            return render_template('threshold.html', title='Possible transaction for '+stockcode +' for threshold '+str(thresh), tables = [threshhold.to_html(classes='threshold')], titles=threshhold.columns.values)

                
        elif request.form['submit_button'] == 'Table':
            print('Getting table, scraping')
            allholders,lastopholders = getallholders(stockcode,sdate,edate)
            maxHold = lastopholders.shareholding_pct.max()
            labels = list(lastopholders['participant_name'])
            values = list(lastopholders['shareholding_pct'])
            return render_template('top_holders.html', title='Top Holders for '+stockcode, max=maxHold, labels=labels, values=values, tables = [allholders.to_html(classes='allholders')], titles=allholders.columns.values)

            
    return render_template('home.html')


def get_holders(stock, date):
    page = selenium.webdriver.Chrome()
    page.get('https://www.hkexnews.hk/sdw/search/searchsdw.aspx')
    wdw(page, 5).until(ec.presence_of_element_located((by.CSS_SELECTOR, 'input[name*="txtStockCode"]')))
    
    scode_element = page.find_element_by_id('txtStockCode')
    scode_element.send_keys(stock)
    
    dateelement = page.find_element_by_id("txtShareholdingDate")
    dateelement.click()
    allholders = pd.DataFrame()
    yearbutton = page.find_element_by_css_selector('b[class*="year"]')
    yearbutton.find_element_by_css_selector('button[data-value*="' + date.strftime('%Y') + '"]').click()
    monthbutton = page.find_element_by_css_selector('b[class*="month"]')
    monthbottontarget = monthbutton.find_element_by_css_selector('button[data-value*="' + str(int(date.strftime('%#m')) - 1) + '"]')
    daybutton = page.find_element_by_css_selector('b[class*="day"]')
    daybutton.find_element_by_css_selector('button[data-value*="' + date.strftime('%#d') + '"]').click()
    dateelement.click()            
    searchelement = page.find_element_by_css_selector('a[id*="btnSearch"]')
    searchelement.click()
    wdw(page, 5).until(ec.presence_of_element_located((by.CSS_SELECTOR, 'table[class*="table table-scroll table-sort table-mobile-list "]')))
    tableelement = page.find_element_by_css_selector('table[class*="table table-scroll table-sort table-mobile-list "]')
    holders = pd.read_html(tableelement.get_attribute('outerHTML'), parse_dates=False)[0]
    holders.columns = ['participant_id','participant_name','participant_address','shareholding','shareholding_pct']
    holders['date'] = date
    holders['participant_name'] = [n.replace(',', '').replace('.', '').replace('"', '').replace("'", '').replace('Name of CCASS Participant (* for Consenting Investor Participants ):  ', '') for n in holders['participant_name']]
    holders['shareholding_pct'] = [float(p.replace('% of the total number of Issued Shares/ Warrants/ Units:', '').replace('%', ''))/100 for p in holders['shareholding_pct']]
    holders['participant_address'] = [''.join([c for c in a.replace('Address:  ', '') if c not in ['/','\\',',','!','.',';','@','%','^','&','*',')','(','"',"'"]]) for a in holders['participant_address']]
    holders['participant_id'] = [n.replace(' ', '')[:10] if i == 'Participant ID:' else i for n,i in zip(holders['participant_name'], holders['participant_id'].str.replace('Participant ID:  ', ''))]
    holders['shareholding'] = holders['shareholding'].str.replace('Shareholding: ', '').str.replace(',', '')
    page.close()              
    
    return holders


def getallholders(stockcode,sdate,edate):
    dates = pd.date_range(sdate,edate)
    allholders = pd.DataFrame()
    for date in dates:
        print('Scraping stockcode ' + stockcode + ' for date: ' +str(date))
        holders = get_holders(stockcode,date)
        allholders = allholders.append(holders)
    lastholders = allholders.loc[allholders['date'] == edate]
    lastholderstop = lastholders.sort_values('shareholding_pct',ascending=False).head(10)
    
    return allholders,lastholderstop
    
def thresholdchange(stockcode,sdate,edate,thresh):
#
#    thresh = 0.00001
#    stockcode = '00012'
    allholders,lastholderstop = getallholders(stockcode,sdate,edate)
    allhold_change = pd.DataFrame()
    for i,g in allholders.groupby('participant_id'):
        g['shareholding_delta'] =  g[['date','shareholding_pct']].sort_values('date').shareholding_pct.diff()
        
        g['shareholding_delta'] = [round(x,5) for x in g['shareholding_delta']]
        allhold_change = allhold_change.append(g)
    reqdf = pd.DataFrame()
    for d in allhold_change.date.unique():
        currdf = allhold_change.loc[allhold_change['date'] == d]
        buy = currdf.loc[currdf.shareholding_delta > thresh]
        buy['transaction'] = 'Buy'
        sell = currdf.loc[currdf.shareholding_delta < (-1*thresh)]
        sell['transaction'] = 'Sell'
        if len(buy)>0 and len(sell)>0:
            reqdf = reqdf.append(buy)
            reqdf = reqdf.append(sell)
            
    return reqdf[['date','transaction','participant_name','shareholding_pct','shareholding_delta']]
    
def main(argv):

    if len(argv) > 0:
        port = int(argv[0])
    else:
        port = 8818

    app.run()

if __name__ == '__main__':

    main(sys.argv[1:])


          
            