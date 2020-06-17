# -*- coding: utf-8 -*-
'''
声明：
这个函数针对文件和文件夹命名编码是如下格式：
1. mac/linux 系统， 默认是utf-8
2. windows 系统， 默认是gb2312， 也可以是utf-8

对于其他编码，我们这里尝试使用chardet这个库进行编码判断， 但是这个并不能保证100% 正确，
建议用户先调试函数，如果有必要改写这个函数，并保证调试通过

函数最新进展可以关注该blog: https://yq.aliyun.com/articles/680958

Statement:
This function names and encodes files and folders as follows:
1. MAC/Linux system, default is utf-8
2. For Windows, the default is gb2312 or utf-8

For other encodings, we try to use the chardet library for coding judgment here, 
but this is not guaranteed to be 100% correct. 
If necessary to rewrite this function, and ensure that the debugging pass
'''

import helper
import oss2, json
import os
import logging
import time

"""
When a source/ prefix object is placed in an OSS, it is hoped that the object will be decompressed and then stored in the OSS as processed/ prefixed.
For example, source/a.zip will be processed as processed/a/... 
"Source /", "processed/" can be changed according to the user's requirements.

detail: https://yq.aliyun.com/articles/680958
"""
# Close the info log printed by the oss SDK
logging.getLogger("oss2.api").setLevel(logging.ERROR)
logging.getLogger("oss2.auth").setLevel(logging.ERROR)


def handler(event, context):
    """
    The object from OSS will be decompressed automatically .
    param: event:   The OSS event json string. Including oss object uri and other information.

    param: context: The function context, including credential and runtime info.

        For detail info, please refer to https://help.aliyun.com/document_detail/56316.html#using-context
    """
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    evt = json.loads(event)
    logger.info("Handling event: %s", evt)

    endpoint = 'https://oss-%s-internal.aliyuncs.com' % context.region
    src_client = get_oss_client(context, endpoint, evt["src_bucket"])
    key = evt["key"]
    max_concurrent = evt.get("max_concurrent", 100)  # foreach concurrent count
    min_count_per_task = evt.get('min_count_per_task', 1000)  # per unzip task handled minimum files count
    max_concurrent = max_concurrent if max_concurrent > 0 else 100
    min_count_per_task = min_count_per_task if min_count_per_task > 0 else 1000

    if "ObjectCreated:PutSymlink" == evt.get('event_name'):
        key = src_client.get_symlink(key).target_key
        logger.info("Resolved target key %s from %s", key, evt["key"])
        if key == "":
            raise RuntimeError('{} is invalid symlink file'.format(key))

    ext = os.path.splitext(key)[1]
    if ext != ".zip":
        raise RuntimeError('{} filetype is not zip'.format(key))

    logger.info("Start to splits zip file %s", key)
    zip_fp = helper.OssStreamFileLikeObject(src_client, key)

    # Splits to multi segments
    with helper.zipfile_support_oss.ZipFile(zip_fp) as zf:
        total = len(zf.namelist())
        groups = split(total, max_concurrent, min_count_per_task)
    logger.info("Split files into %d groups", len(groups))
    return {
        "groups": groups,
    }


def split(total, max_group, min_count_per_group):
    groups = []
    per_count = total // max_group
    per_count = per_count + 1 if total % max_group != 0 else per_count
    per_count = max(per_count, min_count_per_group)

    offset = 0
    for ind in range(max_group):
        cur_count = min(per_count, total)
        groups.append((offset, offset + cur_count - 1))
        total -= cur_count
        if total == 0:
            break
        offset += cur_count

    return groups


def get_oss_client(context, endpoint, bucket):
    creds = context.credentials
    if creds.security_token is not None:
        auth = oss2.StsAuth(creds.access_key_id, creds.access_key_secret, creds.security_token)
    else:
        # for local testing, use the public endpoint
        endpoint = str.replace(endpoint, "-internal", "")
        auth = oss2.Auth(creds.access_key_id, creds.access_key_secret)
    return oss2.Bucket(auth, endpoint, bucket)


if __name__ == '__main__':
    print(split(1000, 100, 1000))
    print(split(1000000, 100, 1000))
