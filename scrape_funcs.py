
import requests
from bs4 import BeautifulSoup
import selenium
import time
import pprint
import pandas as pd

import argparse

from datetime import datetime, timedelta
import numpy as np

from functools import reduce

from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException

from selenium.webdriver.support.wait import WebDriverWait

from selenium.webdriver.support import expected_conditions as EC

from selenium.webdriver.common.by import By

import os


PDGA_URL = "https://www.pdga.com/tour/event"
WEATHER_HISTORY_URL = "https://www.wunderground.com/history/"
DIVS = ['MPO', 'FPO']

# settings for selenium
caps = DesiredCapabilities().CHROME
caps["pageLoadStrategy"] = "none"

pd.set_eng_float_format(accuracy=1, use_eng_prefix=True)

chromedriver = "/Users/kendra/Applications/chromedriver" # path to the chromedriver executable
os.environ["webdriver.chrome.driver"] = chromedriver


def get_tourney_info(id):
    url = f"{PDGA_URL}/{id}"

    try:
        page = requests.get(url)
    except requests.exceptions.RequestException as e:
        print(f"Page not found ({e})")

    if page.status_code == 404:
        print("No tourney associated with this ID")
        return None, None

    page_soup = BeautifulSoup(page.content, 'html.parser')

    tourney_info = {}
    tourney_info['tourney_id'] = id
    t_name = page_soup.find('h1').text
    tourney_info['tourney'] = t_name


    deets = page_soup.find('ul', class_="event-info info-list")
    for x in deets:
        deet = x.text
        if 'Date' in deet:
            date_str = deet.split(": ")[1]
            tourney_info['date_str'] = date_str
            last_date_str = date_str.split(" to ")[1]
            last_dt = datetime.strptime(last_date_str, '%d-%b-%Y')
            first_day_str = date_str.split(" to ")[0]
            first_dt = datetime.strptime(first_day_str + "-" + str(last_dt.year), '%d-%b-%Y')
            tourney_info['t_first_day_dt'] = first_dt
            tourney_info['t_last_day_dt'] = last_dt
        if 'Location' in deet:
            loc_str = deet.split(": ")[1]
            loc_list = loc_str.split(", ")
            tourney_info['c_town'] = loc_list[0]
            tourney_info['c_state'] = loc_list[1]
            tourney_info['c_country'] = loc_list[2]
    
    # number of rounds
    tables = page_soup.find_all(class_="table-container")
    table = tables[1]
    headers = table.find_all('th')
    num_rds = len([x for x in headers if x['class'][0] == 'round'])
    tourney_info['num_rounds'] = num_rds

    return page_soup, tourney_info


def get_round_scores(page_soup, tourney_info):
    label_dict = {1: 'MPO', 2: 'FPO'}
    tables = page_soup.find_all(class_="table-container")
    df_list = []
    num_rds = tourney_info['num_rounds']

    for i, table in enumerate(tables):
        if i == 0: # first table is status / info we don't need
            continue
            
        div = label_dict[i]
        
        # course_par = None # par is different for FPO and MPO
        data_list = []
        
        # headers = table.find_all('th')
        # num_rds = len([x for x in headers if x['class'][0] == 'round'])
        
        all_rows = table.find_all('tr')
        for j, row in enumerate(all_rows):

            if j == 0: # first row is header; skip
                continue

            player_info = {}
            p_name = row.find('td', class_="player").text
            total = row.find('td', class_="total").text

            if total == 'DNF':
                continue
            
            player_info['division'] = div
            player_info['player'] = p_name
            player_info['pdga_num'] = row.find('td', class_="pdga-number").text
            player_info['player_rating'] = int(row.find('td', class_="player-rating").text)

            # oa_score = int(row.find('td', class_="par")['data-text'])
    #         player_info['score'] = oa_score # don't care about this, if looking at by round?
            
            score_html = row.find_all('td', class_="round")
            rating_html = row.find_all('td', class_="round-rating")

            rd_scores = [int(x.text) for x in score_html]
            rd_ratings = [int(x.text) for x in rating_html]
            
            # par = int((np.sum(rd_scores) - oa_score) / 3)
        
            # if not course_par:
            #     course_par = par
            # else:
            #     if par != course_par:
            #         print(f"Par calculations do no agree! Previous consensus par: {course_par}")
            #         print(f"Player: {p_name}, Calc par: {par}, Score: {oa_score}")
            
            t_start_dt = tourney_info['t_first_day_dt']
            
            for k in range(num_rds):            
                round_info = {}
                # rd_date = last_dt - timedelta(days=(nr-(k+1)))
                rd_date = t_start_dt + timedelta(days=k)
                round_info['round'] = k+1
                round_info['round_date'] = rd_date
                round_info['score'] = rd_scores[k]
                round_info['round_rating'] = rd_ratings[k]
                # round_info['score_vs_par'] = rd_scores[k] - par
                
                round_info.update(player_info)        
                data_list.append(round_info)

        table_df = pd.DataFrame.from_dict(data_list)
        df_list.append(table_df)

    data_df = reduce(lambda df1, df2: pd.concat([df1, df2]), df_list)
    # data_df['tourney_id'] = tourney_info['tourney_id']

    return data_df


def get_hole_distances(udisc_url, tourney_info):
    
    driver = webdriver.Chrome(chromedriver, desired_capabilities=caps)

    base_url = '/'.join(udisc_url.split('?')[:-1])
    hole_info_xpath='//*[@id="main-content"]/div/div[3]/div[2]/div[2]/div[1]'

    hole_info_dict = {}
    num_rds = tourney_info['num_rounds']

    # driver.get(udisc_url)
    # xp = '//*[@id="react-root"]/div/div[2]/div[1]/div[1]/div/div[2]/div[4]/div[2]'
    # round_header = driver.find_element_by_xpath(xp)
    # num_rds = len([x for x in round_header.find_elements_by_tag_name('button')])

    for div in DIVS:
        for rd in range(1, num_rds+1):
            page_url = f'{base_url}/{rd}?t=scores&d={div}'
            print(page_url)
            driver.get(page_url)
            time.sleep(5)
            hole_info_list = []
            for i in range(6, 24): # indices of web element div
                hole_xpath = f'{hole_info_xpath}/div[{i}]'
                x = driver.find_element_by_xpath(hole_xpath)
                hole_info_list.append(x.text.split('\n'))

            hole_info_dict[(div, rd)] = hole_info_list

    driver.close()

    df_list = []

    for k, val_list in hole_info_dict.items():
        layout_df = pd.DataFrame(val_list, columns=['hole', 'distance', 'par'])
        layout_df['division'] = k[0]
        layout_df['round'] = k[1]
        layout_df['tourney_id'] = tourney_info['tourney_id']
        df_list.append(layout_df)
    
    hole_info_df = reduce(lambda df1, df2: pd.concat([df1, df2]), df_list)

    return hole_info_df




def find_element(driver, xpath):
    
    element = driver.find_element_by_xpath(xpath)
    if element:
        return element
    else:
        return False

def find_daily_obs_table(driver):
    otxp = "/html/body/app-root/app-history/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div/section/div[2]/div[1]/div[5]/div[1]/div/lib-city-history-observation/div/div[2]/table"                        
    
    element = driver.find_element_by_xpath(otxp)
    if element:
        return element
    else:
        return False
    

def close_privacy_box(driver):
    box = False
    while not box:
        box = find_element(driver, '//*[@id="cdk-overlay-0"]/snack-bar-container/privacy-toast-view/div/button/i')
    box.click()                       


def get_weather_info(tourney_info):

    # -----------------------
    # HISTORY SEARCH PAGE
    # -----------------------
    driver = webdriver.Chrome(chromedriver, desired_capabilities=caps)
    driver.get(WEATHER_HISTORY_URL)

    time.sleep(5)

    # enter city, state in form box
    loc_form = driver.find_element_by_id("historySearch")
    loc_form.clear()
    tourney_loc = f"{tourney_info['c_town']}, {tourney_info['c_state']}"
    loc_form.send_keys(tourney_loc)

    # select first option in autocomplete (assume it's correct...)
    time.sleep(1)
    first_option = driver.find_element_by_xpath('//*[@id="historyForm"]/search-autocomplete/ul')
    first_option.submit()
                       

    # select date
    date_dt = tourney_info['t_first_day_dt']

    month_xpath_base = '//*[@id="dateSelect"]/div/select[1]/option'
    month = datetime.strftime(date_dt, '%B')
    driver.find_element_by_xpath(f"{month_xpath_base}[text()='{month}']").click()

    day_xpath_base = '//*[@id="dateSelect"]/div/select[2]/option'
    driver.find_element_by_xpath(f"{day_xpath_base}[text()='{date_dt.day}']").click()

    year_xpath_base = '//*[@id="dateSelect"]/div/select[3]/option'
    driver.find_element_by_xpath(f"{year_xpath_base}[text()='{date_dt.year}']").click()
    
    # get rid of privacy box
    close_privacy_box(driver)
    
    # submit
    driver.find_element_by_xpath('//*[@id="dateSelect"]/div/input').click()
        

    # -----------------------
    # DAILY HISTORY PAGE
    # -----------------------
    
    actual_loc_element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, 
                                        '//*[@id="inner-content"]/div[1]/lib-city-header/div[1]/div/h1/span[1]')))
    actual_loc = actual_loc_element.text.rstrip(' Weather History')

    history_url = driver.current_url
    history_url_base = "/".join(history_url.split('/')[:-1])

    data_df_list = []
                       
    while date_dt <= tourney_info['t_last_day_dt']:
        date_str = datetime.strftime(date_dt, '%Y-%m-%-d')
        print(date_str)
        next_history_url = history_url_base + '/' + date_str
        if driver.current_url != next_history_url:
            driver.get(next_history_url)
            time.sleep(2)

        # otxp = "/html/body/app-root/app-history/one-column-layout/wu-header/sidenav/mat-sidenav-container/mat-sidenav-content/div/section/div[2]/div[1]/div[5]/div[1]/div/lib-city-history-observation/div/div[2]/table"
        # obs_table = WebDriverWait(driver, 5).until(find_element(driver, otxp))
        obs_table = WebDriverWait(driver, 10).until(find_daily_obs_table)
        table_header = obs_table.find_element_by_tag_name('thead').find_element_by_tag_name('tr')
        headers = [h.text for h in table_header.find_elements_by_tag_name('th')]
        table_data = obs_table.find_element_by_tag_name('tbody')
        data = [[x.text for x in row.find_elements_by_tag_name('td')] for row in table_data.find_elements_by_tag_name('tr')]
        data_df = pd.DataFrame(data=data, columns=headers)
        data_df['date'] = date_dt
        data_df_list.append(data_df)

        # advance to next daily history page
        date_dt += timedelta(days=1)

        
    weather_df = reduce(lambda df1, df2: pd.concat([df1, df2]), data_df_list)
    weather_df['tourney_loc'] = tourney_loc
    weather_df['weather_loc'] = actual_loc
    weather_df['tourney_id'] = tourney_info['tourney_id']

    driver.close()
    return weather_df


def scrape_tourney_data(id):
    """id is tourney id used in PDGA url
    """
    page_soup, tourney_info = get_tourney_info(id)
    if page_soup is None:
        return None


    t_data_df = get_round_scores(page_soup, tourney_info)

    # merge tourney info & data
    t_info_df = pd.DataFrame.from_dict(tourney_info, orient='index').T
    # t_info_df['course_par'] = course_par
    t_info_df['key'] = 'key'
    t_data_df['key'] = 'key'
    tourney_df = pd.merge(t_info_df, t_data_df, on='key').drop(columns='key')

    # get hole distances
    link = page_soup.find('a', {"class": "tour-show-hole-scores-link"}, href=True)['href']
    print(link)
    h_info_df = get_hole_distances(link, tourney_info)
    h_info_df['distance'] = pd.to_numeric(h_info_df['distance'])
    h_info_df['par'] = pd.to_numeric(h_info_df['par'])

    # merge with tourney data
    h_agg_df = h_info_df.groupby(['division', 'round']).agg({'distance':'sum', 'par':'sum'})
    merge_df = tourney_df.merge(h_agg_df, on=['division', 'round'])
    merge_df['score_vs_par'] = merge_df['score']- merge_df['par']

    # get weather info
    # t_weather_df = get_weather_info(tourney_info)
        # ?? How to combine weather with tourney data? Need start times, or to assume things

    # for now, save dataframes
    merge_df.to_pickle(f'./data/round_data_{id}.pkl')
    h_info_df.to_pickle(f'./data/hole_distances_{id}.pkl')
    # t_weather_df.to_pickle(f'./data/weather_data_{id}.pkl')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scrape tournament data')
    
    # a string
    parser.add_argument('-id', 
                        action='store',
                        help='Tournament ID (used in PDGA url)',
                        default=None)
    
    args = parser.parse_args()
    scrape_tourney_data(args.id)