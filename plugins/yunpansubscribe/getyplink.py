from app.schemas.types import MediaType
import requests
import json
from app.log import logger

class GetYpLink():
    # 请求影巢资源id的请求头
    resource_headers = {
        'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
        'Content-Type': 'application/json'
    }
    # 请求云盘链接的请求头
    yunpan_headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-TW;q=0.5",
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTcxOTA0MzkxMSwianRpIjoiYWZlNWE3NGUtNDczZi00MjFiLWJkNDItNzViYjIxYTg3YWQ0IiwidHlwZSI6ImFjY2VzcyIsInN1YiI6NzI4NiwibmJmIjoxNzE5MDQzOTExLCJleHAiOjE3MjE2MzU5MTF9.Vby_NkD_8U9Ce_r2b_MgH0Kx60iFj3jiNXE5kTZoCeg",
        "Connection": "keep-alive",
        "Host": "www.hdhive.org",
        "Origin": "https://hdhive.org",
        "Referer": "https://hdhive.org/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\""
    }
    
    def __init__(self,username:str,password:str):
        self.username = username
        self.password = password
        self.login()

            
    def get_yunpan_link(self,tmdbid:str,mtype:MediaType,title:str):
        if mtype == MediaType.MOVIE:
            resource_url = "https://www.hdhive.org/api/v1/public/movies"
            yunpan_url = "https://www.hdhive.org/api/v1/customer/resources?movie_id=%s&sort_by=is_admin&sort_order=descend&per_page=1000"
        else:
            resource_url = "https://www.hdhive.org/api/v1/public/tv"
            yunpan_url = "https://www.hdhive.org/api/v1/customer/resources?tv_id=%s&sort_by=is_admin&sort_order=descend&per_page=1000"
        res = []
        payload = json.dumps({
            "tmdb_id": tmdbid
        })
        resource_req = requests.request("POST",resource_url, data=payload,headers=self.resource_headers)
        resource_res = json.loads(resource_req.text)
        
        if resource_res['success']:
            resource_id = resource_res['data']['id']
            yunpan_url = yunpan_url % resource_id
            yunpan_req = requests.request("GET", yunpan_url, headers=self.yunpan_headers)
            yunpan_res = json.loads(yunpan_req.text)
            if yunpan_res['success'] and len(yunpan_res['data']) != 0:
                logger.info(f"{title} 成功搜索到 {len(yunpan_res['data'])} 条数据")
                for i in yunpan_res['data']:
                    if any(sub in i['url'] for sub in ['alipan','aliyundrive']):
                        res.append(i['url'])
                return res
        else:
            logger.warn(f"{title} 未搜索到数据")
            return []
  
    def login(self):
        url = 'https://www.hdhive.org/api/v1/login'  
        res = requests.request("POST",url ,headers=self.resource_headers,json={
            'password': self.password,
            'username': self.username
        })
        self.yunpan_headers['Authorization'] = "Bearer " + res.json()["meta"]["access_token"]