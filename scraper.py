import re
import csv
import json
import logging
import requests

from urllib.parse import urljoin
from bs4 import BeautifulSoup

class InsynsbkStockholmScraper(object):
    def __init__(self):
        self.url = 'http://insynsbk.stockholm.se/Byggochplantjansten/Arenden/'
        
        FORMAT = "%(asctime)s [ %(filename)s:%(lineno)s - %(funcName)s() ] %(message)s"
        logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        self.session = requests.Session()

    def csv_save(self, data):
        headers = [
            'Reference Number',
            'Real estate',
            'Case Type',
            'Case Meaning',
            'Start Date'
        ]

        with open('results.csv', 'w') as fp:
            writer = csv.writer(fp, quoting=csv.QUOTE_NONNUMERIC)
            writer.writerow(headers)

            for row in data:
                writer.writerow(row)
        
    def submit_search(self, address):
        '''
        Submit search form for given address
        '''
        resp = self.session.get(self.url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        form = soup.find('form', id='aspnetForm')
        data = []

        # Build the list of inputs
        for i in form.find_all('input', attrs={'name': True}):
            # There are two submit buttons - one for search and one for clear
            # We only want to send the one for search
            if i.get('type') != 'submit' or i.get('name').endswith('SearchButton'):
                # For some reason the HTML comes back without the checkboxes checked
                # even though the browser shows the them as checked by default
                if i['type'] == 'checkbox':
                    if i['id'].endswith('SearchCase_CurrentCasesCheck') or \
                       i['id'].endswith('SearchCase_ArchivedCasesCheck'):
                        data.append((i['name'], 'on'))
                else:
                    data.append((i['name'], i.get('value')))

        # Borough select dropdown
        select = form.find('select')
        option = next(
            o['value'] for o in select.find_all('option')
            if o.get('selected') == 'selected'
        )
        
        data.append((select['name'], option))

        data = dict(data)
        data['__EVENTTARGET'] = None
        data['__EVENTARGUMENT'] = None

        # Fill in the address search field
        k = next(k for k in data.keys() if k.endswith('AddressInput'))
        data[k] = address

        # Now submit the search form
        url = urljoin(self.url, form['action'])

        resp = self.session.post(url, data=data)
        return resp.text

    # Emulate the next page __doPostBack() call
    def goto_page(self, html, pageno):
        soup = BeautifulSoup(html, 'html.parser')
        
        # See if there's a next page and so submit it...
        r = re.compile(r"__doPostBack\('([^']+)','(Page\$%s)" % pageno)        
        page_link = soup.find('a', href=r)

        if page_link is None:
            return None
        
        form = soup.find('form', id='aspnetForm')
        data = []

        for i in form.find_all('input', attrs={'name': True}):
            data.append((i['name'], i.get('value')))
            
        data = dict(data)

        # http://toddhayton.com/2015/05/04/scraping-aspnet-pages-with-ajax-pagination/
        r = re.compile(r"__doPostBack\('([^']+)','([^']+)")
        m = re.search(r, page_link['href'])
            
        data['__EVENTTARGET'] = m.group(1)
        data['__EVENTARGUMENT'] = m.group(2)

        url = urljoin(self.url, form['action'])

        self.logger.info(f'Getting page {pageno}')

        resp = self.session.post(url, data=data)
        html = resp.text

        return html

    def scrape_cases(self, html):
        cases = []
        pageno = 2

        while True:
            soup = BeautifulSoup(html, 'html.parser')

            for tr in soup.select('table.DataGrid > tr'):
                td = tr.find_all('td', attrs={'class': 'DataGridItemCell'})
                if len(td) > 0:
                    cases.append([t.text.strip() for t in td])

            html = self.goto_page(html, pageno)
            if html is None:
                break

            pageno += 1

        self.logger.info(f'Scraped {len(cases)} cases')
        return cases
    
    def scrape(self):
        address = 'Fleminggatan 4'
        self.logger.info(f'Submitting search for address {address}')
        
        html = self.submit_search(address)
        cases = self.scrape_cases(html)

        self.csv_save(cases)
        
if __name__ == '__main__':
    scraper = InsynsbkStockholmScraper()
    scraper.scrape()
