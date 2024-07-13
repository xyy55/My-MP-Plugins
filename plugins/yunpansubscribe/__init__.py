from threading import Lock
from typing import Optional, Any, List, Dict, Tuple
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import pytz
from app.core.config import settings

from app.plugins import _PluginBase
from app.db.subscribe_oper import SubscribeOper

from .subscribe import SubscribeChain
from app.log import logger



lock = Lock()


class YunpanSubscibe(_PluginBase):
    # 插件名称
    plugin_name = "云盘订阅"
    # 插件描述
    plugin_desc = "通过订阅寻找云盘资源，并通过alist下载"
    # 插件图标
    plugin_icon = "cloud.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "xyy"
    # 作者主页
    author_url = None
    # 插件配置项ID前缀
    plugin_config_prefix = "yunpansubscibe_"
    # 加载顺序
    plugin_order = 3
    # 可使用的用户级别
    auth_level = 1

    # 私有变量
    _scheduler: Optional[BackgroundScheduler] = None
    subscribechain = None
    subscribeoper = None

    # 配置属性
    _enabled: bool = False
    _onlyonce: bool = False
    _cron: str = ""
    _notify: bool = False
    _alist_link: str = ""
    _aria_rpc: str = ""
    _aria_token: str = ""
    _alist_user: str = ""
    _alist_password: str = ""
    _hdhive_user: str = ""
    _hdhive_password: str = ""
    
    def init_plugin(self, config: dict = None):
        #停止现有任务
        self.stop_service()
        
        #配置
        if config:
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._notify = config.get("notify")
            self._onlyonce = config.get("onlyonce")
            self._alist_link = config.get("alist_link")
            self._aria_rpc = config.get("aria_rpc")
            self._aria_token = config.get("aria_token")
            self._alist_user = config.get("alist_user")
            self._alist_password = config.get("alist_password")
            self._hdhive_user = config.get("hdhive_user")
            self._hdhive_password = config.get("hdhive_password")
            data = {
                "enabled": self._enabled,
                "notify": self._notify,
                "onlyonce": self._onlyonce,
                "cron": self._cron,
                "alist_link":self._alist_link,
                "aria_rpc":self._aria_rpc,
                "aria_token":self._aria_token,
                "alist_user":self._alist_user,
                "alist_password":self._alist_password,
                "hdhive_user":self._hdhive_user,
                "hdhive_password":self._hdhive_password
            }
            self.subscribechain = SubscribeChain(data)

        if self._enabled or self._onlyonce:
            if self._onlyonce:
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                logger.info(f"云盘订阅服务启动，立即运行一次")
                self._scheduler.add_job(func=self.sync, trigger='date',
                                        run_date=datetime.datetime.now(
                                            tz=pytz.timezone(settings.TZ)) + datetime.timedelta(seconds=3)
                                        )

                # 启动任务
                if self._scheduler.get_jobs():
                    self._scheduler.print_jobs()
                    self._scheduler.start()
            
            if self._onlyonce:
                # 关闭一次性开关
                self._onlyonce = False
                self.__update_config()
        
        
    def get_api(self) -> List[Dict[str, Any]]:
        pass
    def get_command() -> List[Dict[str, Any]]:
        pass
    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '发送通知',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '5位cron表达式，留空自动'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'alist_link',
                                            'label': 'alist地址',
                                            'placeholder': '例：http://192.168.1.1:5244'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'aria_rpc',
                                            'label': 'aria rpc链接',
                                            'placeholder': '例：http://192.168.1.1:6800/jsonrpc'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'aria_token',
                                            'label': 'aria2 token',
                                            'placeholder': 'aria2 token'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'alist_user',
                                            'label': 'alist用户名',
                                            'placeholder': 'alist用户名'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'alist_password',
                                            'label': 'alist密码',
                                            'placeholder': 'alist密码'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'hdhive_user',
                                            'label': 'hdhive用户名',
                                            'placeholder': 'hdhive用户名'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'hdhive_password',
                                            'label': 'hdhive密码',
                                            'placeholder': 'hdhive密码'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                ]
            }
        ],{
            "enabled": False,
            "notify": True,
            "onlyonce": False,
            "cron": "*/30 * * * *",
            "alist_link":"",
            "aria_rpc":"",
            "aria_token":"",
            "alist_user":"",
            "alist_password":"",
            "hdhive_user":"",
            "hdhive_password":""
            
        }
    def get_page(self) -> List[dict]:
        """
        拼装插件详情页面，需要返回页面配置，同时附带数据
        """
        # 查询订阅详情
        self.subscribeoper = SubscribeOper()
        subscribes = self.subscribeoper.list()
        if not subscribes:
            return [
                {
                    'component': 'div',
                    'text': '暂无数据',
                    'props': {
                        'class': 'text-center',
                    }
                }
            ]
        # 数据按时间降序排序
        subscribes = sorted(subscribes, key=lambda x: x.id, reverse=True)
        # 拼装页面
        contents = []
        for subscribe in subscribes:
            title = subscribe.name
            poster = subscribe.poster
            mtype = subscribe.type
            time_str = subscribe.year
            doubanid = subscribe.doubanid
            contents.append(
                {
                    'component': 'VCard',
                    'content': [
                        {
                            'component': 'div',
                            'props': {
                                'class': 'd-flex justify-space-start flex-nowrap flex-row',
                            },
                            'content': [
                                {
                                    'component': 'div',
                                    'content': [
                                        {
                                            'component': 'VImg',
                                            'props': {
                                                'src': poster,
                                                'height': 120,
                                                'width': 80,
                                                'aspect-ratio': '2/3',
                                                'class': 'object-cover shadow ring-gray-500',
                                                'cover': True
                                            }
                                        }
                                    ]
                                },
                                {
                                    'component': 'div',
                                    'content': [
                                        {
                                            'component': 'VCardTitle',
                                            'props': {
                                                'class': 'ps-1 pe-5 break-words whitespace-break-spaces'
                                            },
                                            'content': [
                                                {
                                                    'component': 'a',
                                                    'props': {
                                                        'href': f"https://movie.douban.com/subject/{doubanid}",
                                                        'target': '_blank'
                                                    },
                                                    'text': title
                                                }
                                            ]
                                        },
                                        {
                                            'component': 'VCardText',
                                            'props': {
                                                'class': 'pa-0 px-2'
                                            },
                                            'text': f'类型：{mtype}'
                                        },
                                        {
                                            'component': 'VCardText',
                                            'props': {
                                                'class': 'pa-0 px-2'
                                            },
                                            'text': f'年份：{time_str}'
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            )

        return [
            {
                'component': 'div',
                'props': {
                    'class': 'grid gap-3 grid-info-card',
                },
                'content': contents
            }
        ]
    def get_state(self) -> bool:
        pass
    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error("退出插件失败：%s" % str(e))

    def sync(self):
        """
        开始搜索订阅的云盘资源
        """
        print('开始搜索')
        if not self._alist_link or not self._aria_rpc or not self._alist_user or not self._alist_password or not self._hdhive_user or not self._hdhive_password:
            print('sdaaweac')
            return
        self.subscribechain.search(state='N')
        self.subscribechain.search(state='R')
        
    def __update_config(self):
        """
        更新配置
        """
        self.update_config({
            "enabled": self._enabled,
            "notify": self._notify,
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "alist_link":self._alist_link,
            "aria_rpc":self._aria_rpc,
            "aria_token":self._aria_token,
            "alist_user":self._alist_user,
            "alist_password":self._alist_password,
            "hdhive_user":self._hdhive_user,
            "hdhive_password":self._hdhive_password
        })



