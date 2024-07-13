import json
import random
import time
from datetime import datetime
from json import JSONDecodeError
from typing import Dict, List, Union, Tuple
import copy

from app.chain import ChainBase
from app.chain.download import DownloadChain
from app.chain.search import SearchChain
from app.core.config import settings
from app.core.context import  Context, MediaInfo
from app.core.event import  EventManager
from app.core.meta import MetaBase
from app.core.metainfo import MetaInfo
from app.db.models.subscribe import Subscribe
from app.db.site_oper import SiteOper
from app.db.subscribe_oper import SubscribeOper
from app.db.subscribehistory_oper import SubscribeHistoryOper
from app.db.systemconfig_oper import SystemConfigOper
from app.helper.message import MessageHelper
from app.helper.subscribe import SubscribeHelper
from app.log import logger
from app.schemas import NotExistMediaInfo, Notification
from app.schemas.types import MediaType, SystemConfigKey, MessageChannel, NotificationType, EventType

from .getyplink import GetYpLink
from .aliyunapi import Aliyunapi
from app.core.metainfo import MetaInfoPath
from pathlib import Path


class SubscribeChain(ChainBase):
    """
    订阅管理处理链
    """

    def __init__(self,data:dict):
        super().__init__()
        self.downloadchain = DownloadChain()
        self.searchchain = SearchChain()
        self.subscribeoper = SubscribeOper()
        self.subscribehistoryoper = SubscribeHistoryOper()
        self.subscribehelper = SubscribeHelper()
        self.message = MessageHelper()
        self.systemconfig = SystemConfigOper()
        self.siteoper = SiteOper()
        self.getyplink = GetYpLink(data["hdhive_user"],data["hdhive_password"])
        self.aliyunapi = Aliyunapi(data["alist_link"],data["aria_rpc"],data["aria_token"],data["alist_user"],data["alist_password"])

    

    def search(self, sid: int = None, state: str = 'N', manual: bool = False):
        """
        订阅搜索
        :param sid: 订阅ID，有值时只处理该订阅
        :param state: 订阅状态 N:未搜索 R:已搜索
        :param manual: 是否手动搜索
        :return: 更新订阅状态为R或删除订阅
        """
        if sid:
            subscribes = [self.subscribeoper.get(sid)]
        else:
            subscribes = self.subscribeoper.list(state)
        # 遍历订阅
        for subscribe in subscribes:
            mediakey = subscribe.tmdbid or subscribe.doubanid
            # 校验当前时间减订阅创建时间是否大于1分钟，否则跳过先，留出编辑订阅的时间
            if subscribe.date:
                now = datetime.now()
                subscribe_time = datetime.strptime(subscribe.date, '%Y-%m-%d %H:%M:%S')
                if (now - subscribe_time).total_seconds() < 60:
                    logger.debug(f"订阅标题：{subscribe.name} 新增小于1分钟，暂不搜索...")
                    continue
            # 随机休眠1-5分钟
            if not sid and state == 'R':
                # sleep_time = random.randint(60, 300)
                sleep_time = 1
                logger.info(f'订阅搜索随机休眠 {sleep_time} 秒 ...')
                time.sleep(sleep_time)
            logger.info(f'开始搜索订阅，标题：{subscribe.name} ...')
            # 如果状态为N则更新为R
            if subscribe.state == 'N':
                self.subscribeoper.update(subscribe.id, {'state': 'R'})
            # 生成元数据
            meta = MetaInfo(subscribe.name)
            meta.year = subscribe.year
            meta.begin_season = subscribe.season or None
            try:
                meta.type = MediaType(subscribe.type)
            except ValueError:
                logger.error(f'订阅 {subscribe.name} 类型错误：{subscribe.type}')
                continue
            # 识别媒体信息
            mediainfo: MediaInfo = self.recognize_media(meta=meta, mtype=meta.type,
                                                        tmdbid=subscribe.tmdbid,
                                                        doubanid=subscribe.doubanid,
                                                        cache=False)
            if not mediainfo:
                logger.warn(
                    f'未识别到媒体信息，标题：{subscribe.name}，tmdbid：{subscribe.tmdbid}，doubanid：{subscribe.doubanid}')
                continue

            # 非洗版状态
            if not subscribe.best_version:
                # 每季总集数
                totals = {}
                if subscribe.season and subscribe.total_episode:
                    totals = {
                        subscribe.season: subscribe.total_episode
                    }
                # 查询媒体库缺失的媒体信息
                exist_flag, no_exists = self.downloadchain.get_no_exists_info(
                    meta=meta,
                    mediainfo=mediainfo,
                    totals=totals
                )
            else:
                # 洗版状态
                exist_flag = False
                if meta.type == MediaType.TV:
                    no_exists = {
                        mediakey: {
                            subscribe.season: NotExistMediaInfo(
                                season=subscribe.season,
                                episodes=[],
                                total_episode=subscribe.total_episode,
                                start_episode=subscribe.start_episode or 1)
                        }
                    }
                else:
                    no_exists = {}

            # 已存在
            if exist_flag:
                logger.info(f'{mediainfo.title_year} 媒体库中已存在')
                self.finish_subscribe_or_not(subscribe=subscribe, meta=meta, mediainfo=mediainfo, force=True)
                continue

            # 电视剧订阅处理缺失集
            if meta.type == MediaType.TV:
                # 实际缺失集与订阅开始结束集范围进行整合，同时剔除已下载的集数
                no_exists = self.__get_subscribe_no_exits(
                    subscribe_name=f'{subscribe.name} {meta.season}',
                    no_exists=no_exists,
                    mediakey=mediakey,
                    begin_season=meta.begin_season,
                    total_episode=subscribe.total_episode,
                    start_episode=subscribe.start_episode,
                    downloaded_episodes=self.__get_downloaded_episodes(subscribe)
                )

            # 搜索，同时电视剧会过滤掉不需要的剧集
            context = self.process(mediainfo=mediainfo,
                                    keyword=subscribe.keyword,
                                    no_exists=no_exists)
            if not context:
                logger.warn(f'订阅 {subscribe.keyword or subscribe.name} 未搜索到资源')
                self.finish_subscribe_or_not(subscribe=subscribe, meta=meta,
                                             mediainfo=mediainfo, lefts=no_exists)
                continue
            
            

            # 自动下载
            downloads, lefts = self.batch_download(
                context=context,
                no_exists=no_exists,
                userid=subscribe.username,
                username=subscribe.username,
                save_path=subscribe.save_path
            )


            # 判断是否应完成订阅
            self.finish_subscribe_or_not(subscribe=subscribe, meta=meta, mediainfo=mediainfo,
                                         downloads=downloads, lefts=lefts)

        # 手动触发时发送系统消息
        if manual:
            if sid:
                self.message.put(f'{subscribes[0].name} 搜索完成！', title="订阅搜索", role="system")
            else:
                self.message.put('所有订阅搜索完成！', title="订阅搜索", role="system")

    def process(self, mediainfo: MediaInfo,
                keyword: str = None,
                no_exists: Dict[int, Dict[int, NotExistMediaInfo]] = None) -> List[Context]:
        """
        根据媒体信息搜索种子资源，精确匹配，应用过滤规则，同时根据no_exists过滤本地已存在的资源
        :param mediainfo: 媒体信息
        :param keyword: 搜索关键词
        :param no_exists: 缺失的媒体信息
        """
        # 豆瓣标题处理
        if not mediainfo.tmdb_id:
            meta = MetaInfo(title=mediainfo.title)
            mediainfo.title = meta.name
            mediainfo.season = meta.begin_season
        logger.info(f'开始搜索资源，关键词：{keyword or mediainfo.title} ...')

        # 补充媒体信息
        if not mediainfo.names:
            mediainfo: MediaInfo = self.recognize_media(mtype=mediainfo.type,
                                                        tmdbid=mediainfo.tmdb_id,
                                                        doubanid=mediainfo.douban_id)
            if not mediainfo:
                logger.error(f'媒体信息识别失败！')
                return []
            
        links = self.getyplink.get_yunpan_link(mediainfo.tmdb_id,mediainfo.type,mediainfo.title)
        if not links:
            logger.warn(f'暂无云盘资源！！')
            return None
        
        links = self.aliyunapi.check_valid(links)
        
        for link in links:
            print(link)
        
        contexts = {'meta_info':MetaInfo(title=mediainfo.title),
                    'media_info':mediainfo,
                    'links':links}
        return contexts
    
    def batch_download(self,
                       context,
                       no_exists: Dict[Union[int, str], Dict[int, NotExistMediaInfo]] = None,
                       save_path: str = None,
                       channel: MessageChannel = None,
                       userid: str = None,
                       username: str = None
                       ) -> Tuple[List[Context], Dict[Union[int, str], Dict[int, NotExistMediaInfo]]]:
        """
        根据缺失数据，自动种子列表中组合择优下载
        :param contexts:  资源上下文列表
        :param no_exists:  缺失的剧集信息
        :param save_path:  保存路径
        :param channel:  通知渠道
        :param userid:  用户ID
        :param username: 调用下载的用户名/插件名
        :return: 已经下载的资源列表、剩余未下载到的剧集 no_exists[tmdb_id/douban_id] = {season: NotExistMediaInfo}
        """
        # files
        # {
        #     'share_token': 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJjdXN0b21Kc29uIjoie1wiZG9tYWluX2lkXCI6XCJiajI5XCIsXCJzaGFyZV9pZFwiOlwiQU5nRlVIU3lhNzVcIixcImNyZWF0b3JcIjpcImQ1MGIxOTMwYTNjNDRlYTQ4NzdmNjViMTQ1ODExMGM4XCIsXCJ1c2VyX2lkXCI6XCJhbm9ueW1vdXNcIn0iLCJjdXN0b21UeXBlIjoic2hhcmVfbGluayIsImV4cCI6MTcxOTg1MjI5OSwiaWF0IjoxNzE5ODQ1MDM5fQ.aBhyIKR9RxXZ1iKrKjVXZWWEw8hlPqcGHVRniELp0Dfdkc6vYQGPYRwik8shXtlchWJR20GM9045BbP7jGxzxYoIwtlZ2kBCwGCh95ttLq0XqZtYYGY-1vf7WwFSzxMxGYo-aWOXTBKj0s1xQwWYxTq8Ejzk3_mVRodD67OvAKk',
        #     'file_id': '66629f8271510e3280444838ad439613b8c428b3',
        #     'share_id': 'ANgFUHSya75',
        #     'path': '/末@路#狂￥花&钱（2024）/2024.2160p.WEB-DL.H265.EDR.DDP5.1-BestWEB.mkv'
        # }
        
        # 已下载的项目
        downloaded_list = []

        def __update_seasons(_mid: Union[int, str], _need: list, _current: list) -> list:
            """
            更新need_tvs季数，返回剩余季数
            :param _mid: TMDBID
            :param _need: 需要下载的季数
            :param _current: 已经下载的季数
            """
            # 剩余季数
            need = list(set(_need).difference(set(_current)))
            # 清除已下载的季信息
            seas = copy.deepcopy(no_exists.get(_mid))
            if seas:
                for _sea in list(seas):
                    if _sea not in need:
                        no_exists[_mid].pop(_sea)
                    if not no_exists.get(_mid) and no_exists.get(_mid) is not None:
                        no_exists.pop(_mid)
                        break
            return need

        def __update_episodes(_mid: Union[int, str], _sea: int, _need: list, _current: set) -> list:
            """
            更新need_tvs集数，返回剩余集数
            :param _mid: TMDBID
            :param _sea: 季数
            :param _need: 需要下载的集数
            :param _current: 已经下载的集数
            """
            # 剩余集数
            need = list(set(_need).difference(set(_current)))
            if need:
                not_exist = no_exists[_mid][_sea]
                no_exists[_mid][_sea] = NotExistMediaInfo(
                    season=not_exist.season,
                    episodes=need,
                    total_episode=not_exist.total_episode,
                    start_episode=not_exist.start_episode
                )
            else:
                no_exists[_mid].pop(_sea)
                if not no_exists.get(_mid) and no_exists.get(_mid) is not None:
                    no_exists.pop(_mid)
            return need

        def __get_season_episodes(_mid: Union[int, str], season: int) -> int:
            """
            获取需要的季的集数
            """
            if not no_exists.get(_mid):
                return 9999
            no_exist = no_exists.get(_mid)
            if not no_exist.get(season):
                return 9999
            return no_exist[season].total_episode

        # 如果是电影，直接下载
        if context['media_info'].type == MediaType.MOVIE:
            logger.info(f"开始下载电影 {context['media_info'].title} ...")
            is_downloaded = False
            for link in context['links']:
                if is_downloaded:
                    break
                files = self.aliyunapi.get_list_by_share(link['share_id'])
                for file in files:
                    if is_downloaded:
                        break
                    path = '/'+context['media_info'].title+file['path']
                    is_downloaded = self.aliyunapi.save_file(file['share_token'],file['file_id'],file['share_id'],path)
                    downloaded_list.append(context)
                    
        elif context['media_info'].type == MediaType.TV:
            if no_exists:
                need_tv_list = list(no_exists)
                for need_mid in need_tv_list:
                    need_tv = no_exists.get(need_mid)
                    if not need_tv:
                        continue
                    need_tv_copy = copy.deepcopy(no_exists.get(need_mid))
                    # 循环每一季
                    for sea, tv in need_tv_copy.items():
                        # 当前需要季
                        need_season = sea
                        # 当前需要集
                        need_episodes = tv.episodes
                        # TMDB总集数
                        total_episode = tv.total_episode
                        # 需要开始集
                        start_episode = tv.start_episode or 1
                        # 缺失整季的转化为缺失集进行比较
                        if not need_episodes:
                            need_episodes = list(range(start_episode, total_episode + 1))
                        logger.info(f"开始下载电视剧 {context['media_info'].title} ...")
                        for link in context['links']:
                            files = self.aliyunapi.get_list_by_share(link['share_id'])
                            for file in files:
                                path = '/'+context['media_info'].title+file['path']
                                sub_path = Path(path)
                                meta = MetaInfoPath(sub_path)
                                episodes = set()
                                for i in range(meta.total_episode):
                                    episodes.add(meta.begin_episode + i)
                                print(episodes)
                                if episodes.issubset(set(need_episodes)) and need_season == meta.begin_season:
                                    logger.info(f"开始下载 {meta.title} 集数 {episodes}...")
                                    need_episodes = __update_episodes(_mid=need_mid,
                                                                    _need=need_episodes,
                                                                    _sea=need_season,
                                                                    _current=episodes)
                                    logger.info(f"季 {need_season} 剩余需要集：{need_episodes}")
                                    self.aliyunapi.save_file(file['share_token'],file['file_id'],file['share_id'],path)
                    downloaded_list.append(context)
                    
                                    
                                    
                                
        logger.info(f"成功下载资源数：{len(downloaded_list)}，剩余未下载的剧集：{no_exists}")
        return downloaded_list, no_exists
            


    def update_subscribe_priority(self, subscribe: Subscribe, meta: MetaInfo,
                                  mediainfo: MediaInfo, downloads: List[Context]):
        """
        更新订阅已下载资源的优先级
        """
        if not downloads:
            return
        if not subscribe.best_version:
            return
        # 当前下载资源的优先级
        priority = max([item.torrent_info.pri_order for item in downloads])
        if priority == 100:
            # 洗版完成
            self.__finish_subscribe(subscribe=subscribe, meta=meta, mediainfo=mediainfo, bestversion=True)
        else:
            # 正在洗版，更新资源优先级
            logger.info(f'{mediainfo.title_year} 正在洗版，更新资源优先级为 {priority}')
            self.subscribeoper.update(subscribe.id, {
                "current_priority": priority
            })

    def finish_subscribe_or_not(self, subscribe: Subscribe, meta: MetaInfo, mediainfo: MediaInfo,
                                downloads: List[Context] = None,
                                lefts: Dict[Union[int | str], Dict[int, NotExistMediaInfo]] = None,
                                force: bool = False):
        """
        判断是否应完成订阅
        """
        mediakey = subscribe.tmdbid or subscribe.doubanid
        # 是否有剩余集
        no_lefts = not lefts or not lefts.get(mediakey)
        # 是否完成订阅
        if not subscribe.best_version:
            # 非洗板
            if ((no_lefts and meta.type == MediaType.TV)
                    or (downloads and meta.type == MediaType.MOVIE)
                    or force):
                # 完成订阅
                self.__finish_subscribe(subscribe=subscribe, meta=meta, mediainfo=mediainfo)
            elif downloads and meta.type == MediaType.TV:
                # 电视剧更新已下载集数
                self.__update_subscribe_note(subscribe=subscribe, downloads=downloads)
                # 更新订阅剩余集数和时间
                self.__update_lack_episodes(lefts=lefts, subscribe=subscribe,
                                            mediainfo=mediainfo, update_date=True)
            else:
                # 未下载到内容且不完整
                logger.info(f'{mediainfo.title_year} 未下载完整，继续订阅 ...')
                if meta.type == MediaType.TV:
                    # 更新订阅剩余集数
                    self.__update_lack_episodes(lefts=lefts, subscribe=subscribe,
                                                mediainfo=mediainfo, update_date=False)
        elif downloads:
            # 洗板，下载到了内容，更新资源优先级
            self.update_subscribe_priority(subscribe=subscribe, meta=meta,
                                           mediainfo=mediainfo, downloads=downloads)
        else:
            # 洗版，未下载到内容
            logger.info(f'{mediainfo.title_year} 继续洗版 ...')
        """
        获取订阅过滤规则，同时组合默认规则
        """
        # 默认过滤规则
        default_rule = self.systemconfig.get(SystemConfigKey.DefaultFilterRules) or {}
        return {
            "include": subscribe.include or default_rule.get("include"),
            "exclude": subscribe.exclude or default_rule.get("exclude"),
            "quality": subscribe.quality or default_rule.get("quality"),
            "resolution": subscribe.resolution or default_rule.get("resolution"),
            "effect": subscribe.effect or default_rule.get("effect"),
            "tv_size": default_rule.get("tv_size"),
            "movie_size": default_rule.get("movie_size"),
            "min_seeders": default_rule.get("min_seeders"),
            "min_seeders_time": default_rule.get("min_seeders_time"),
        }

    def __update_subscribe_note(self, subscribe: Subscribe, downloads: List[Context]):
        """
        更新已下载集数到note字段
        """
        # 查询现有Note
        if not downloads:
            return
        note = []
        if subscribe.note:
            try:
                note = json.loads(subscribe.note)
            except JSONDecodeError:
                note = []
        for context in downloads:
            meta = context.meta_info
            mediainfo = context.media_info
            if mediainfo.type != MediaType.TV:
                continue
            if subscribe.tmdbid and mediainfo.tmdb_id \
                    and mediainfo.tmdb_id != subscribe.tmdbid:
                continue
            if subscribe.doubanid and mediainfo.douban_id \
                    and mediainfo.douban_id != subscribe.doubanid:
                continue
            episodes = meta.episode_list
            if not episodes:
                continue
            # 合并已下载集
            note = list(set(note).union(set(episodes)))
            # 更新订阅
            self.subscribeoper.update(subscribe.id, {
                "note": json.dumps(note)
            })

    @staticmethod
    def __get_downloaded_episodes(subscribe: Subscribe) -> List[int]:
        """
        获取已下载过的集数
        """
        if not subscribe.note:
            return []
        if subscribe.type != MediaType.TV.value:
            return []
        try:
            episodes = json.loads(subscribe.note)
            logger.info(f'订阅 {subscribe.name} 第{subscribe.season}季 已下载集数：{episodes}')
            return episodes
        except JSONDecodeError:
            logger.warn(f'订阅 {subscribe.name} note字段解析失败')
        return []

    def __update_lack_episodes(self, lefts: Dict[Union[int, str], Dict[int, NotExistMediaInfo]],
                               subscribe: Subscribe,
                               mediainfo: MediaInfo,
                               update_date: bool = False):
        """
        更新订阅剩余集数
        """
        if not lefts:
            return
        mediakey = subscribe.tmdbid or subscribe.doubanid
        left_seasons = lefts.get(mediakey)
        if left_seasons:
            for season_info in left_seasons.values():
                season = season_info.season
                if season == subscribe.season:
                    left_episodes = season_info.episodes
                    if not left_episodes:
                        lack_episode = season_info.total_episode
                    else:
                        lack_episode = len(left_episodes)
                    logger.info(f'{mediainfo.title_year} 季 {season} 更新缺失集数为{lack_episode} ...')
                    if update_date:
                        # 同时更新最后时间
                        self.subscribeoper.update(subscribe.id, {
                            "lack_episode": lack_episode,
                            "last_update": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                    else:
                        self.subscribeoper.update(subscribe.id, {
                            "lack_episode": lack_episode
                        })

    def __finish_subscribe(self, subscribe: Subscribe, mediainfo: MediaInfo,
                           meta: MetaBase, bestversion: bool = False):
        """
        完成订阅
        """
        # 完成订阅
        msgstr = "订阅"
        if bestversion:
            msgstr = "洗版"
        logger.info(f'{mediainfo.title_year} 完成{msgstr}')
        # 新增订阅历史
        self.subscribehistoryoper.add(**subscribe.to_dict())
        # 删除订阅
        self.subscribeoper.delete(subscribe.id)
        # 发送通知
        if mediainfo.type == MediaType.TV:
            link = settings.MP_DOMAIN('#/subscribe-tv?tab=mysub')
        else:
            link = settings.MP_DOMAIN('#/subscribe-movie?tab=mysub')
        self.post_message(Notification(mtype=NotificationType.Subscribe,
                                       title=f'{mediainfo.title_year} {meta.season} 已完成{msgstr}',
                                       image=mediainfo.get_message_image(),
                                       link=link))
        # 发送事件
        EventManager().send_event(EventType.SubscribeComplete, {
            "subscribe_id": subscribe.id,
            "subscribe_info": subscribe.to_dict(),
            "mediainfo": mediainfo.to_dict(),
        })
        # 统计订阅
        self.subscribehelper.sub_done_async({
            "tmdbid": mediainfo.tmdb_id,
            "doubanid": mediainfo.douban_id
        })

    @staticmethod
    def __get_subscribe_no_exits(subscribe_name: str,
                                 no_exists: Dict[Union[int, str], Dict[int, NotExistMediaInfo]],
                                 mediakey: Union[str, int],
                                 begin_season: int,
                                 total_episode: int,
                                 start_episode: int,
                                 downloaded_episodes: List[int] = None):
        """
        根据订阅开始集数和总集数，结合TMDB信息计算当前订阅的缺失集数
        :param subscribe_name: 订阅名称
        :param no_exists: 缺失季集列表
        :param mediakey: TMDB ID或豆瓣ID
        :param begin_season: 开始季
        :param total_episode: 订阅设定总集数
        :param start_episode: 订阅设定开始集数
        :param downloaded_episodes: 已下载集数
        """
        # 使用订阅的总集数和开始集数替换no_exists
        if not no_exists or not no_exists.get(mediakey):
            return no_exists
        no_exists_item = no_exists.get(mediakey)
        if total_episode or start_episode:
            logger.info(f'订阅 {subscribe_name} 设定的开始集数：{start_episode}、总集数：{total_episode}')
            # 该季原缺失信息
            no_exist_season = no_exists_item.get(begin_season)
            if no_exist_season:
                # 原集列表
                episode_list = no_exist_season.episodes
                # 原总集数
                total = no_exist_season.total_episode
                # 原开始集数
                start = no_exist_season.start_episode

                # 更新剧集列表、开始集数、总集数
                if not episode_list:
                    # 整季缺失
                    episodes = []
                    start_episode = start_episode or start
                    total_episode = total_episode or total
                else:
                    # 部分缺失
                    if not start_episode \
                            and not total_episode:
                        # 无需调整
                        return no_exists
                    if not start_episode:
                        # 没有自定义开始集
                        start_episode = start
                    if not total_episode:
                        # 没有自定义总集数
                        total_episode = total
                    # 新的集列表
                    new_episodes = list(range(max(start_episode, start), total_episode + 1))
                    # 与原集列表取交集
                    episodes = list(set(episode_list).intersection(set(new_episodes)))
                # 更新集合
                no_exists[mediakey][begin_season] = NotExistMediaInfo(
                    season=begin_season,
                    episodes=episodes,
                    total_episode=total_episode,
                    start_episode=start_episode
                )
        # 根据订阅已下载集数更新缺失集数
        if downloaded_episodes:
            logger.info(f'订阅 {subscribe_name} 已下载集数：{downloaded_episodes}')
            # 该季原缺失信息
            no_exist_season = no_exists_item.get(begin_season)
            if no_exist_season:
                # 原集列表
                episode_list = no_exist_season.episodes
                # 原总集数
                total = no_exist_season.total_episode
                # 原开始集数
                start = no_exist_season.start_episode
                # 更新剧集列表
                episodes = list(set(episode_list).difference(set(downloaded_episodes)))
                # 更新集合
                no_exists[mediakey][begin_season] = NotExistMediaInfo(
                    season=begin_season,
                    episodes=episodes,
                    total_episode=total,
                    start_episode=start
                )
            else:
                # 开始集数
                start = start_episode or 1
                # 不存在的季
                no_exists[mediakey][begin_season] = NotExistMediaInfo(
                    season=begin_season,
                    episodes=list(set(range(start, total_episode + 1)).difference(set(downloaded_episodes))),
                    total_episode=total_episode,
                    start_episode=start
                )
        logger.info(f'订阅 {subscribe_name} 缺失剧集数更新为：{no_exists}')
        return no_exists
