from app.core.metainfo import MetaInfoPath
from pathlib import Path
from app.chain.transfer import TransferChain
from app.helper.aliyun import AliyunHelper
from app.utils.http import RequestUtils
from time import sleep
from app.chain.download import DownloadChain
from .alistdownload import AlistDownload



class Aliyunapi():
    # no_exists
    # {
    #     229202 : {
    #         1 : NotExistMediaInfo(season = 1, episodes = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38], total_episode = 38, start_episode = 2)
    #     }
    # }
    
    # meta
    # MetaVideo(isfile = True, title = 'The.Tale.of.Rose.2024.S01E01.2160p.WEB-DL.HEVC.10bit.DV.DDP.2Audios.mp4', 
    #           org_string = 'The.Tale.of.Rose.2024.S01E01.2160p.WEB-DL.HEVC.10bit.DV.DDP.2Audios', 
    #           subtitle = None, type = <MediaType.TV: '电视剧' > , cn_name = None, en_name = 'The Tale Of Rose', year = '2024', 
    #           total_season = 1, begin_season = 1, end_season = None, total_episode = 1, begin_episode = 1, end_episode = None, part = None, 
    #           resource_type = 'WEB-DL', resource_effect = 'DV', resource_pix = '2160p', resource_team = None, customization = None, 
    #           video_encode = 'HEVC 10bit', audio_encode = 'DDP 2Audios', apply_words = [], tmdbid = None, doubanid = None)
    
    # 转存文件url
    save_file_url = 'https://api.aliyundrive.com/adrive/v4/batch'
    # 获取分享文件url
    share_file_url = 'https://api.aliyundrive.com/adrive/v2/file/list_by_share'
    aliyunhelper = AliyunHelper()
    alistdownload = None
    params = aliyunhelper.get_access_params()
    share_token = ''
    
    def __init__(self,alist_link,aria_rpc,aria_token,alist_user,alist_password):
        self.alistdownload = AlistDownload(alist_link,aria_rpc,aria_token,alist_user,alist_password)

        
    
    def save_file(self,share_token,file_id,share_id,path = ''):
        downloadchain = DownloadChain()
        transferchain = TransferChain()
        
        sub_path = Path(path)
        meta = MetaInfoPath(sub_path)
        mediainfo = transferchain.recognize_media(meta)
        
        if  mediainfo:
            # 每季总集数
            exist_flag, no_exists = downloadchain.get_no_exists_info(
                meta=meta,
                mediainfo=mediainfo,
                # totals=totals
            )
            
            if not exist_flag:
                # 如果资源不存在就开始转存
                url = 'https://api.aliyundrive.com/adrive/v4/batch'
                headers = {
                    'Authorization':f"Bearer {self.params.get('accessToken')}",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
                    "x-canary": "client=web,app=share,version=v2.3.1",
                    "x-device-id": self.params.get('x_device_id'),
                    "x-share-token": share_token,
                }
                data = {
                    "requests": [{
                        "body": {
                            "file_id": file_id,
                            "share_id": share_id,
                            "auto_rename": True,
                            "to_parent_file_id": "650c15b477f3b32301254eeca2a35b33a918f853",
                            "to_drive_id": "713979182"
                        },
                        "headers": {
                            "Content-Type": "application/json"
                        },
                        "id": "0",
                        "method": "POST",
                        "url": "/file/copy"
                    }],
                    "resource": "file"
                }
                res = RequestUtils(headers=headers, timeout=10).post_res(url, json=data)
                new_path = TransferChain().recommend_name(meta=meta, mediainfo=mediainfo)
                if res and new_path:
                    new_name = Path(new_path).name
                    new_file_id = res.json()['responses'][0]['body']['file_id']
                    # 转存完成后开始重命名
                    succ = self.aliyunhelper.rename(new_file_id,new_name)
                    print(succ)
                    if succ:
                        self.alistdownload.download(new_name)
                        return True
        return False
            
    def get_list_by_share(self,share_id, parent_file_id='root', share_pwd="",path=''):
        # {
        #     'items': [{
        #         'drive_id': '1104127930',
        #         'domain_id': 'bj29',
        #         'file_id': '6664e689b22682ab81d1471aad969083c83e2bb3',
        #         'share_id': 'MTtM4zdMcUt',
        #         'name': '玫瑰的故事(2024)4K 杜比视界',
        #         'type': 'folder',
        #         'created_at': '2024-06-08T23:17:29.111Z',
        #         'updated_at': '2024-06-08T23:17:29.111Z',
        #         'parent_file_id': '6631e934b3ce8d582a544b4ab779cdf5686d8ed1'
        #     }],
        #     'next_marker': ''
        # }

        self.share_token=self.get_share_token(share_id=share_id)

        url = "https://api.aliyundrive.com/adrive/v2/file/list_by_share"
        headers = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
            "x-canary": "client=web,app=share,version=v2.3.1",
            "x-device-id": "2nZcHZsF5AoBASQIgnCfKv7S",
            "x-share-token": self.share_token,
        }
        json = {
            "share_id": share_id,
            "parent_file_id": parent_file_id,
            "limit": 200,
            "image_thumbnail_process": "image/resize,w_256/format,jpeg",
            "image_url_process": "image/resize,w_1920/format,jpeg/interlace,1",
            "video_thumbnail_process": "video/snapshot,t_1000,f_jpg,ar_auto,w_256",
            "order_by": "name",
            "order_direction": "ASC",
        }
        res = RequestUtils(headers=headers, timeout=30).post_res(url, json=json)
        ret=[]
        files = []
        if res:
            res_json = res.json()
            for item in res_json['items']:
                ret.append(item)

            while res.json()["next_marker"] != "":
                sleep(1)
                json["marker"] = res_json["next_marker"]
                res_json = RequestUtils(headers=headers, timeout=10).post_res(url, json=json).json()
                if res_json["items"]:
                    for item in res_json['items']:
                        ret.append(item)
                        
        for item in ret:
            if item['type'] == 'folder':
                sleep(1)
                files = files + self.get_list_by_share(share_id=share_id,parent_file_id=item['file_id'],path=path+'/'+item['name'])
            elif item['type'] == 'file' and 'video' in item['mime_type']:
                files.append({'share_token':self.share_token,
                              'file_id':item['file_id'],
                              'share_id':share_id,
                              'path':path+'/'+item['name'],
                              'file_size':item['size']})
            else:
                continue
        return files
    
    def get_share_token(self,share_id, share_pwd=""):
        url="https://api.aliyundrive.com/v2/share_link/get_share_token"
        
        headers = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
            "x-canary": "client=web,app=share,version=v2.3.1",
            "x-device-id": "2nZcHZsF5AoBASQIgnCfKv7S",
            "Content-Type": "application/json",
        }
        res = RequestUtils(headers=headers, timeout=10).post_res(url, json={
            "share_id": share_id, 
            "share_pwd": share_pwd
        })
        if res:
            return res.json()['share_token']
        else:
            return None
   
    def check_valid(self,links):
        valid_links = []
        for link in links:
            # id = 'KQMGrx1Xprc'
            id = link.split("/")[-1]
            url = 'https://api.aliyundrive.com/adrive/v3/share_link/get_share_by_anonymous?share_id=%s'
            url = url % id
            headers = {
                'Authorization':f"Bearer {self.params.get('accessToken')}",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
                "x-canary": "client=web,app=share,version=v2.3.1",
                "x-device-id": self.params.get('x_device_id'),
            }
            res = RequestUtils(headers=headers, timeout=10).post_res(url,json={'share_id':id}).json()
            try:
                res["code"]
            except:
                valid_links.append({'link':link,'share_id':id})
            
        return valid_links

        
            