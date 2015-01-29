#!/usr/bin/env python

import sys
import os
import subprocess
import boto.ec2
import boto.utils
import argparse
import MySQLdb


def parse_args():
    parser = argparse.ArgumentParser(description='snapshot EBS volumes')

    parser.add_argument('mountpoint', help='mount point of volume to snapshot')
    parser.add_argument('-n', '--dry-run', action='store_true', help='help text')
    parser.add_argument('--access-key-id')
    parser.add_argument('--secret-access-key')
    parser.add_argument('-r', '--region', default='us-east-1', help='EC2 region of EBS volume (default: %(default)s)')
    parser.add_argument('--mysql-host')
    parser.add_argument('--mysql-user')
    parser.add_argument('--mysql-password')

    args = parser.parse_args()
    return args


def find_dependencies(config):
    pass


def get_block_device(mountpoint):
    print "searching for block device mounted at", mountpoint

    mounts = {}
    with open('/proc/mounts', 'r') as proc_mounts:
        lines = proc_mounts.read().splitlines()
    for line in lines:
        columns = line.split(' ')
        mounts[columns[1]] = columns[0]
    return mounts[mountpoint]


def connect_ec2(config):
    print "connecting to EC2"

    conn = boto.ec2.connect_to_region(config.region,
                                      aws_access_key_id=config.access_key_id,
                                      aws_secret_access_key=config.secret_access_key)
    return conn


def get_volume_id(conn, block_device):
    print "searching for EBS volume ID of", block_device

    instance_id = boto.utils.get_instance_metadata()['instance-id']
    volumes = conn.get_all_volumes(filters={
        'attachment.instance-id': instance_id})
    for volume in volumes:
        if volume.attach_data.device == block_device:
            return volume.id
        if volume.attach_data.device.replace('/dev/xv', '/dev/s'):
            return volume.id
    return None


def connect_mysql(config):
    print "connecting to MySQL"

    conn = MySQLdb.connect(host=config.mysql_host, user=config.mysql_user,
                           passwd=config.mysql_password, db='')
    return conn.cursor()


def lock_mysql(mysql):
    print "running FLUSH TABLES WITH READ LOCK"
    mysql.execute('FLUSH TABLES WITH READ LOCK')


def freeze_fs(mountpoint):
    print "freezing filesystem mounted at", mountpoint
    proc = subprocess.check_output(['/sbin/fsfreeze', '-f', mountpoint])
    print 'fsfreeze -f returned: %s' % proc


def snapshot(conn, volume_id):
    print "taking snapshot of", volume_id
    return conn.create_snapshot(volume_id)


def unfreeze_fs(mountpoint):
    print "unfreezing filesystem mounted at", mountpoint
    proc = subprocess.check_output(['/sbin/fsfreeze', '-u', mountpoint])
    print 'fsfreeze -u returned: %s' % proc


def unlock_mysql(mysql):
    print "running UNLOCK TABLES"
    mysql.execute('UNLOCK TABLES')


def declare_victory():
    print "VICTORY IS MINE"


def main():
    config = parse_args()
    conn = connect_ec2(config)

    mysql = None

    try:
        block_device = get_block_device(config.mountpoint)
        volume_id = get_volume_id(conn, block_device)
        mysql = connect_mysql(config)
        lock_mysql(mysql)
        freeze_fs(config.mountpoint)
        print snapshot(conn, volume_id)
    except Exception, e:
        print "ERROR encountered: %s: %s" % (type(e), e)
        print "will attempt to unfreeze filesystem and unlock MySQL..."
    finally:
        unfreeze_fs(config.mountpoint)

        if mysql:
            unlock_mysql(mysql)
    else:
        declare_victory()


if __name__ == '__main__':
    sys.exit(main())