import requests
from urllib import parse
import json
import time
 
 
class AlistDownload():
    
    host = ''
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9"
    }
    token = ''
    
    def __init__(self, alist_link,aria_rpc,aria_token,alist_user,alist_password):
        self.alist_user = alist_user
        self.alist_password = alist_password
        self.aria_rpc = aria_rpc
        self.aria_token = aria_token
        parseresult = parse.urlparse(alist_link)
        scheme = parseresult.scheme
        netloc = parseresult.netloc
        self.host = f"{scheme}://{netloc}"
        self.token = self.get_token()
        self.headers['Authorization'] = self.token
    
    def get_token(self):
        data = {
            "username": self.alist_user,
            "password": self.alist_password
        }
        res = requests.post(url=self.host+'/api/auth/login', data=json.dumps(data), headers=self.headers, timeout=15)
        if res.json()['code'] == 200:
            return res.json()['data']['token']
        return None
    
    def download(self,file_name):
        api = self.aria_rpc
        id = "QXJpYU5nXzE2NzUxMzUwMDFfMC42Mzc0MDA5MTc2NjAzNDM="
        url = self.host + "/d" + '/阿里云盘/来自分享/' + file_name
        data = {
            "id": id,
            "jsonrpc": "2.0",
            "method": "aria2.addUri",
            "params": ["token:"+self.aria_token,[url], {"dir": '/downloads', "out": file_name,"check-certificate":"false","header": ["Authorization: "+self.token]}]
        }
        if file_name in self.get_list('/阿里云盘/来自分享/'):
            req = requests.post(url=api, data=json.dumps(data))
            return_json = req.json()
            print(return_json)
 
    def get_list(self, path):
        url = self.host + "/api/fs/list"
        data = {"path": path, "password": "", "page": 1, "per_page": 0, "refresh": True}
        file_list = []
        error_number = 0
        while True:
            req_json = requests.post(url=url, data=json.dumps(data),headers=self.headers).json()
            if req_json.get("code") == 200:
                break
            elif error_number > 2:
                break
            else:
                error_number += 1
                time.sleep(2)
        if req_json.get("data") is None:
            return []
        content = req_json.get("data")["content"]
        if content is None:
            return []
        for file_info in content:
            if not file_info["is_dir"]:
                file_list.append(file_info["name"])
        return file_list
        
 
    