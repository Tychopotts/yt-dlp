import json
import re

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none,
    traverse_obj,
    truncate_string,
    url_or_none,
    urlencode_postdata,
)


class ThreadsIE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?threads\.(?:net|com)/@(?P<uploader>[^/]+)/post/(?P<id>[a-zA-Z0-9_-]+)'
    _THREADS_DOC_ID = '5587632691339264'
    _THREADS_APP_ID = '238260118697367'
    _REFERER = 'https://www.threads.net/'
    _TESTS = [{
        'url': 'https://www.threads.com/@alongcvsreceipt/post/DXcAKZhiX7E',
        'info_dict': {
            'id': '3880977693487496900',
            'ext': 'mp4',
            'uploader': 'alongcvsreceipt',
            'title': str,
            'timestamp': int,
            'upload_date': r're:\d{8}',
        },
        'params': {
            'skip_download': True,
        },
    }, {
        'url': 'https://www.threads.net/@alongcvsreceipt/post/DXcLLb1lcwQ',
        'info_dict': {
            'id': r're:\d+|DXcLLb1lcwQ',
            'title': str,
        },
        'playlist_mincount': 2,
        'params': {
            'skip_download': True,
        },
    }, {
        'url': 'https://www.threads.net/@alongcvsreceipt/post/DXcLsgUlcNF',
        'info_dict': {
            'id': r're:\d+|DXcLsgUlcNF',
            'title': str,
        },
        'playlist_count': 2,
        'params': {
            'skip_download': True,
        },
    }]

    def _parse_threads_url(self, value, video_id):
        if not isinstance(value, str):
            return None
        url = url_or_none(value)
        if url:
            return url
        if '\\' in value:
            return url_or_none(self._parse_json(json.dumps(value), video_id, fatal=False))
        return None

    def _extract_numeric_post_id(self, webpage, video_id):
        numeric_id = self._search_regex(
            (r'"post_id"\s*:\s*"(\d+)"', r'"pk"\s*:\s*"(\d+)"'),
            webpage, 'post id', default=None)
        scoped_numeric_id = self._search_regex(
            (rf'"(?:code|shortcode)"\s*:\s*"{re.escape(video_id)}".{{0,400}}"pk"\s*:\s*"(\d+)"',
             rf'"pk"\s*:\s*"(\d+)".{{0,400}}"(?:code|shortcode)"\s*:\s*"{re.escape(video_id)}"'),
            webpage, 'scoped post id', default=None)
        return scoped_numeric_id or numeric_id

    def _extract_video_formats(self, media, video_id):
        video_versions = traverse_obj(media, ('video_versions', {list})) or []
        formats = []
        for version in video_versions:
            video_url = self._parse_threads_url(version.get('url'), video_id)
            if not video_url:
                continue
            formats.append({
                'url': video_url,
                'width': int_or_none(version.get('width')),
                'height': int_or_none(version.get('height')),
            })
        formats.sort(key=lambda x: ((x.get('width') or 0) * (x.get('height') or 0), x.get('width') or 0))
        return formats

    def _extract_video_entries(self, media_data, video_id, uploader, default_title):
        entries = []
        seen_ids = set()
        for idx, candidate in enumerate(media_data or [], 1):
            if not isinstance(candidate, dict):
                continue
            media_type = int_or_none(candidate.get('media_type'))
            if media_type not in (None, 2):
                continue
            formats = self._extract_video_formats(candidate, video_id)
            if not formats:
                continue
            media_pk = int_or_none(traverse_obj(candidate, 'pk', 'id'))
            media_id = str(media_pk) if media_pk else f'{video_id}_{idx}'
            if media_id in seen_ids:
                continue
            seen_ids.add(media_id)
            entry_title = traverse_obj(
                candidate, ('caption', 'text'), ('text_post_app_info', 'text'), 'text', expected_type=str)
            entry_title = truncate_string(re.sub(r'\s+', ' ', entry_title).strip(), left=72) if entry_title else None
            entries.append({
                'id': media_id,
                'title': entry_title or default_title,
                'timestamp': int_or_none(traverse_obj(candidate, 'taken_at', 'taken_at_timestamp')),
                'uploader': uploader,
                'formats': formats,
                'http_headers': {
                    'Referer': self._REFERER,
                },
            })
        return entries

    def _find_media_data(self, data):
        media_data = []
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue

            if traverse_obj(item, ('video_versions', {list})) or int_or_none(item.get('media_type')) in (1, 2):
                media_data.append(item)
            stack.extend(item.values())
        return media_data

    def _find_post_media(self, data, numeric_id):
        media_data = []
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            if str(item.get('pk') or item.get('id') or '') == numeric_id:
                media_data.extend(self._find_media_data(item))
            stack.extend(item.values())
        return media_data

    def _find_shortcode_media(self, data, video_id):
        media_data = []
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            shortcode = str(item.get('code') or item.get('shortcode') or '')
            if shortcode == video_id:
                media_data.extend(self._find_media_data(item))
            stack.extend(item.values())
        return media_data

    def _extract_formats_from_webpage(self, webpage, video_id):
        formats = []
        for mobj in re.finditer(r'"(?:video_url|playable_url)"\s*:\s*"([^"]+)"', webpage):
            if video_url := self._parse_threads_url(mobj.group(1), video_id):
                formats.append({'url': video_url})
        for mobj in re.finditer(r'"(https:\\/\\/[^"]+\\.mp4[^"]*)"', webpage):
            if video_url := self._parse_threads_url(mobj.group(1), video_id):
                formats.append({'url': video_url})
        return formats

    def _extract_media_from_sjs(self, webpage, numeric_id, video_id):
        media_data = []
        for mobj in re.finditer(
                r'<script type="application/json"[^>]+data-sjs[^>]*>(\{.+?\})</script>', webpage):
            script_json = mobj.group(1)
            try:
                data = json.loads(script_json)
            except json.JSONDecodeError:
                continue
            media_data.extend(self._find_post_media(data, numeric_id))
            if not media_data:
                media_data.extend(self._find_shortcode_media(data, video_id))
        return media_data

    def _download_graphql(self, endpoint, video_id, *, data=None, query=None, headers=None):
        return self._download_json(
            endpoint, video_id, data=data, query=query, headers=headers,
            fatal=False, errnote=False, impersonate=True) or {}

    def _extract_context(self, url):
        uploader, video_id = self._match_valid_url(url).group('uploader', 'id')
        webpage = self._download_webpage(url, video_id, headers={
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        }, impersonate=True)
        lsd = self._search_regex(
            r'"LSD",\[\],\{"token":"([^"]+)"\}', webpage, 'lsd token', default=None)
        next_data = self._search_nextjs_data(webpage, video_id, default={})
        post_data = traverse_obj(
            next_data,
            ('props', 'pageProps', 'post'),
            ('props', 'pageProps', 'postData'),
            expected_type=dict) or {}
        numeric_id = self._extract_numeric_post_id(webpage, video_id)
        if not numeric_id:
            numeric_id = str(int_or_none(traverse_obj(post_data, 'post_id', 'pk', 'id'))) if int_or_none(
                traverse_obj(post_data, 'post_id', 'pk', 'id')) else None
        return {
            'uploader': uploader,
            'video_id': video_id,
            'webpage': webpage,
            'lsd': lsd,
            'next_data': next_data,
            'post_data': post_data,
            'numeric_id': numeric_id,
        }

    def _fetch_graphql_media_data(self, url, video_id, numeric_id, lsd):
        if not lsd:
            raise ExtractorError('Unable to extract LSD token for Threads GraphQL handshake', expected=True)

        variables = json.dumps({'postID': numeric_id}, separators=(',', ':'))
        graphql_headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'threads-client',
            'X-IG-App-ID': self._THREADS_APP_ID,
            'X-FB-LSD': lsd,
            'Sec-Fetch-Mode': 'cors',
            'Origin': 'https://www.threads.net',
            'Referer': url,
        }

        graphql_data = self._download_graphql(
            'https://www.threads.net/api/graphql', video_id, data=urlencode_postdata({
                'doc_id': self._THREADS_DOC_ID,
                'lsd': lsd,
                'variables': variables,
            }), headers=graphql_headers)
        if not traverse_obj(graphql_data, ('data', 'data', {dict})):
            graphql_data = self._download_graphql(
                'https://www.threads.net/api/graphql', video_id, data=urlencode_postdata({
                    'doc_id': self._THREADS_DOC_ID,
                    'variables': variables,
                }), headers=graphql_headers)
        if not traverse_obj(graphql_data, ('data', 'data', {dict})):
            graphql_data = self._download_graphql(
                'https://www.threads.com/api/graphql', video_id, query={
                    'doc_id': self._THREADS_DOC_ID,
                    'variables': variables,
                    'lsd': lsd,
                }, headers={k: v for k, v in graphql_headers.items() if k != 'Content-Type'})

        temp_post = traverse_obj(graphql_data, ('data', 'data', 'tempPostItem'), expected_type=dict) or {}
        return (
            traverse_obj(temp_post, ('carousel_media', ..., {dict}))
            or traverse_obj(temp_post, ('sidecar_children', ..., {dict}))
            or traverse_obj(temp_post, ({dict},))
            or [])

    def _discover_media_data(self, url, *, video_id, numeric_id, lsd, post_data, next_data, webpage):
        media_data = self._find_post_media(post_data, numeric_id)
        requires_graphql = not media_data or not traverse_obj(media_data, (0, 'video_versions', {list}))
        if requires_graphql:
            media_data = self._fetch_graphql_media_data(url, video_id, numeric_id, lsd) or media_data
        if not media_data:
            media_data = self._find_media_data(next_data)
        if not media_data:
            media_data = self._find_shortcode_media(next_data, video_id)
        if not media_data:
            media_data = self._extract_media_from_sjs(webpage, numeric_id, video_id)
        return media_data

    def _real_extract(self, url):
        context = self._extract_context(url)
        uploader, video_id = context['uploader'], context['video_id']
        webpage, numeric_id = context['webpage'], context['numeric_id']

        if not numeric_id:
            raise ExtractorError('Unable to extract numeric post id for Threads GraphQL', expected=True)

        media_data = self._discover_media_data(url, video_id=video_id, numeric_id=numeric_id, lsd=context['lsd'],
                                               post_data=context['post_data'], next_data=context['next_data'],
                                               webpage=webpage)
        title = self._html_search_meta(['og:title', 'twitter:title'], webpage, default=None)
        title = truncate_string(re.sub(r'\s+', ' ', title).strip(), left=72) if isinstance(title, str) else None
        default_title = title or f'Threads video by {uploader}'
        entries = self._extract_video_entries(media_data, video_id, uploader, default_title)
        if not entries:
            if formats := self._extract_formats_from_webpage(webpage, video_id):
                return {
                    'id': numeric_id or video_id,
                    'title': default_title,
                    'timestamp': int_or_none(self._search_regex(
                        r'"taken_at"\s*:\s*(\d+)', webpage, 'timestamp', fatal=False)),
                    'uploader': uploader,
                    'formats': formats,
                    'http_headers': {
                        'Referer': self._REFERER,
                    },
                }
            raise ExtractorError('No video found in this Threads post', expected=True)
        if len(entries) > 1:
            return self.playlist_result(entries, playlist_id=numeric_id or video_id, playlist_title=default_title)
        return {
            **entries[0],
            'id': entries[0].get('id') or numeric_id or video_id,
        }
