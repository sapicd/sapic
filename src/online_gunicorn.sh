#!/bin/bash
#
#使用gunicorn启动, 要求系统安装了gunicorn, gevent
#

dir=$(cd $(dirname $0); pwd)
cd $dir

procname=$(python -c "from config import GLOBAL;print(GLOBAL['ProcessName'])")

[ -d ${dir}/logs ] || mkdir -p ${dir}/logs
pidfile=${dir}/logs/${procname}.pid
cfg="picbed.py"

function Monthly2Number() {
    case "$1" in
        Jan) echo 1;;
        Feb) echo 2;;
        Mar) echo 3;;
        Apr) echo 4;;
        May) echo 5;;
        Jun) echo 6;;
        Jul) echo 7;;
        Aug) echo 8;;
        Sep) echo 9;;
        Oct) echo 10;;
        Nov) echo 11;;
        Dec) echo 12;;
        *)   exit;;
    esac
}

case $1 in
start)
    if [ -f $pidfile ]; then
        echo "Has pid($(cat $pidfile)) in $pidfile, please check, exit." ; exit 1
    else
        gunicorn app:app -c $cfg
        sleep 1
        pid=$(cat $pidfile)
        [ "$?" != "0" ] && exit 1
        echo "$procname start over with pid ${pid}"
    fi
    ;;

run)
    #前台运行
    picbed_isrun=true gunicorn app:app -c $cfg
    ;;

stop)
    if [ ! -f $pidfile ]; then
        echo "$pidfile does not exist, process is not running"
    else
        echo "Stopping ${procname}..."
        pid=$(cat $pidfile)
        kill -TERM $pid
        sleep 0.2
        while [ -x /proc/${pid} ]
        do
            echo "Waiting for ${procname} to shutdown ..."
            kill -QUIT $pid ; sleep 0.5
        done
        echo "${procname} stopped"
        rm -f $pidfile
    fi
    ;;

status)
    if [ ! -f $pidfile ]; then
        echo -e "\033[39;31m${procname} has stopped.\033[0m"
        exit
    fi
    pid=$(cat $pidfile)
    procnum=$(ps aux | grep -v grep | grep $pid | grep $procname | wc -l)
    m=$(ps -eO lstart | grep $pid | grep $procname | grep -v grep | awk '{print $3}')
    t=$(Monthly2Number $m)
    if [[ "$procnum" != "1" ]]; then
        echo -e "\033[39;31m异常，pid文件与系统pid数量不相等。\033[0m"
        echo -e "\033[39;34m  pid数量：${procnum}\033[0m"
        echo -e "\033[39;34m  pid文件：${pid}($pidfile)\033[0m"
    else
        echo -e "\033[39;33m${procname}\033[0m":
        echo "  pid: $pid"
        echo -e "  state:" "\033[39;32mrunning\033[0m"
        echo -e "  process start time:" "\033[39;32m$(ps -eO lstart | grep $pid | grep $procname | grep -v grep | awk '{print $6"-"$3"-"$4,$5}' | sed "s/${m}/${t}/")\033[0m"
        echo -e "  process running time:" "\033[39;32m$(ps -eO etime| grep $pid | grep $procname | grep -v grep | awk '{print $2}')\033[0m"
    fi
    ;;

reload)
    if [ -f $pidfile ]; then
        kill -HUP $(cat $pidfile)
    fi
    ;;

restart)
    bash $(basename $0) stop
    bash $(basename $0) start
    ;;

*)
    echo "Usage: $0 start|run|stop|reload|restart|status"
    ;;
esac