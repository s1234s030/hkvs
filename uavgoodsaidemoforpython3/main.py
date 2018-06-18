# -*- coding:utf-8 -*-
import time
import sys
import socket
import json
from pathFinder import pathFinder

#从服务器接收一段字符串, 转化成字典的形式
def RecvJuderData(hSocket):
    nRet = -1
    Message = hSocket.recv(1024*10)
    len_json = int(Message[:8])
    str_json = Message[8:].decode()
    while len(str_json) != len_json:
        Message = hSocket.recv(1024)
        str_json = str_json + Message.decode()
    nRet = 0
    Dict = json.loads(str_json)
#    print('received\n',Dict)
    return nRet, Dict

# 接收一个字典,将其转换成json文件,并计算大小,发送至服务器
def SendJuderData(hSocket, dict_send):
#    print('sent\n',dict_send)
    str_json = json.dumps(dict_send)
    len_json = str(len(str_json)).zfill(8)
    str_all = len_json + str_json
    ret = hSocket.sendall(str_all.encode())
    if ret == None:
        ret = 0
    return ret

def main(szIp, nPort, szToken):
    print("server ip %s, prot %d, token %s\n", szIp, nPort, szToken)

    #Need Test // 开始连接服务器
    hSocket = socket.socket()

    hSocket.connect((szIp, nPort))

    #接受数据  连接成功后，Judger会返回一条消息：
    nRet, _ = RecvJuderData(hSocket)
    if (nRet != 0):
        return nRet    

    # // 生成表明身份的json
    token = {}
    token['token'] = szToken        
    token['action'] = "sendtoken"   
    
    #// 选手向裁判服务器表明身份(Player -> Judger)
    nRet = SendJuderData(hSocket, token)
    if nRet != 0:
        return nRet

    #//身份验证结果(Judger -> Player), 返回字典Message
    nRet, Message = RecvJuderData(hSocket)
    if nRet != 0:
        return nRet
    
    if Message["result"] != 0:
        print("token check error\n")
        return -1

    # // 选手向裁判服务器表明自己已准备就绪(Player -> Judger)
    stReady = {}
    stReady['token'] = szToken
    stReady['action'] = "ready"

    nRet = SendJuderData(hSocket, stReady)
    if nRet != 0:
        return nRet

    # //对战开始通知(Judger -> Player)
    nRet, Message = RecvJuderData(hSocket)
    if nRet != 0:
        return nRet
    
    #初始化地图信息
    pstMapInfo = Message["map"]  
    #初始化路径查找对象
    finder = pathFinder(pstMapInfo)    
    #初始化比赛状态信息
    pstMatchStatus = {}
    pstMatchStatus["time"] = 0

    #每一步的飞行计划
    FlyPlane_send = {}
    FlyPlane_send["token"] = szToken
    FlyPlane_send["action"] = "flyPlane"
#    print(finder.prices)
    #发送初始位置    
    UAV_info = finder.init_UAV
    FlyPlane_send['UAV_info'] = [{'no': UAV['no'], 'x': UAV['x'], 'y': UAV['y'], 'z': UAV['z'], "remain_electricity":UAV["remain_electricity"],'goods_no': UAV['goods_no'],}\
                                  for UAV in UAV_info]

    print('time',pstMatchStatus["time"])
    nRet = SendJuderData(hSocket, FlyPlane_send)
    if nRet != 0:
        return nRet
   #接收下一步信息
    nRet, pstMatchStatus = RecvJuderData(hSocket)
    if nRet != 0:
        return nRet 
    t = 0
    # // 根据服务器指令，不停的接受发送数据
    while True:
        time_start=time.time()
        # // 进行当前时刻的数据计算, 填充飞行计划，注意：0时刻不能进行移动，即第一次进入该循环时
        FlyPlane = finder.doStep(pstMatchStatus)
        
        FlyPlane_send['UAV_info'] = FlyPlane[0]        
        FlyPlane_send['purchase_UAV'] = FlyPlane[1]
#        if len(FlyPlane[0])<4:break
        print(pstMatchStatus["time"]) 
        
        # //发送飞行计划
        nRet = SendJuderData(hSocket, FlyPlane_send)
        
        if nRet != 0:
            return nRet
#        if t>0.8:
#            break
        # // 接受当前比赛状态
        nRet, pstMatchStatus = RecvJuderData(hSocket)
        if nRet != 0:
            return nRet
        
        if pstMatchStatus["match_status"] == 1:
            print("game over, we value ", pstMatchStatus["we_value"], "enemy value ",pstMatchStatus["enemy_value"] )
            hSocket.close()
            return 0
        time_end=time.time()
        t = max(time_end-time_start,t)
        print('totally cost',t)

if __name__ == "__main__":
    if len(sys.argv) == 4:
        print("Server Host: " + sys.argv[1])
        print("Server Port: " + sys.argv[2])
        print("Auth Token: " + sys.argv[3])
        main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
    else:
        print("need 3 arguments")
#    main("localhost", 4010, "5f46ffffae76ebf484fb2ba3307909203311ba56")
#    main("123.56.15.18", 30619, "1dfa27f9-a3e8-4027-90f7-ddd3fe0639fb")