# -*- coding: utf-8 -*-    
#import random
import copy
import heapq
import numpy as np 

class pathFinder:
    def __init__(self, flymap): 
        #生成地图
        self.map = np.array([[list('.' * flymap["map"]["z"]) \
                      for _ in range(flymap["map"]["y"])] for _ in range(flymap["map"]["x"])])
        #停机坪
        self.parking = (flymap["parking"]['x'],flymap["parking"]['y'])
        #可飞范围
        self.h_low, self.h_high = flymap["h_low"], flymap["h_high"]
        #生成建筑物
        for building in flymap["building"]:
            self.map[building["x"]:(building["x"]+building["l"]),building["y"]:(building["y"]+building["w"]),0:building["h"]] = 'x'
        #无人机价格
        self.prices = {price['type']:price for price in flymap["UAV_price"]}
        #最便宜飞机类型
        self.chape_type = sorted(self.prices.values(),key = lambda x:x["value"])[0]["type"]
        #地图范围
        self.length, self.width, self.height = flymap["map"]["x"], flymap["map"]["y"], flymap["map"]["z"]        
        #驱逐机
        self.clear_plane = {}    
        #驱逐机个数
        self.clear_num = round(6*self.length/100)    
        #初始化飞机加入空闲
        self.init_UAV = flymap["init_UAV"]
        #飞机加入充电字典和驱逐飞机字典
        self.charge = {}
        for UAV in self.init_UAV:
            if UAV['type'] ==self.chape_type and len(self.clear_plane)<self.clear_num:
                self.clear_plane[UAV['no']] = UAV
            else:
                self.charge[UAV['no']] = UAV 
        #飞机空闲字典
        self.idle = {}
        #已工作飞机统计
        self.busy = {}
        #一次路径规划标志
        self.flag = 0
        #现有飞机统计
        self.type = {}
        for price in self.prices.keys():
            self.type[price]=[]
        for no, plane in self.charge.items():            
            self.type[plane['type']].append(no)
        #限定飞机上限
        self.flaneNum = 4*self.length//20
        #计算每类飞机个数
        self.cluNum(flymap["UAV_price"])
#        print(self.prices)
        #安全区高度
        self.safe = self.h_low -1
        #记录地方飞机位置
        self.pos_enemy = {}
        #我方飞机周围
        self.xs1 = (-1, 0, 1, -1, 1, -1, 0, 1)  
        self.ys1 = (-1,-1,-1,  0, 0,  1, 1, 1)
#        #敌方飞机范围
#        self.xs2 = ( 2, 2, 2, 2, 2, 1, 1, 0, 0,-1,-1,-2,-2,-2,-2,-2)  
#        self.ys2 = (-2,-1, 0, 1, 2,-2, 2,-2, 2,-2, 2,-2,-1, 0, 1, 2)
        #停机坪上方空间
        self.parking_up = set((self.parking[0],self.parking[1],i) for i in range(1,self.h_high))
        self.charge_flag = 0
        #敌方停机坪
        self.enPaking = None
    
        
    def doStep(self, data):
        #记录时间              
        time = data['time']
        #更新我方飞机字典并返回我方飞机位置       
        pos_we = self.update_plane(data['UAV_we'])      
        #更新敌方飞机字典并返回敌方飞机位置及下一步位置
        nextpos_enemy,pos_enemy = self.update_enemy(data['UAV_enemy'])
        #记录敌方停机坪
        if time == 1:
            self.enPaking = (pos_enemy[-1][0],pos_enemy[-1][1])
        #字典形式存储货物信息
        goods = {good['no']:good for good in data['goods']}   
#        print([good['weight'] for good in data['goods']])
        #记录忙的货物编号
        good_busy_no = [good_no for _,_,_,_,good_no in self.busy.values()]
        #将没有安排飞机并且未捡走的货物加入good_idle
        good_idle = {good_no: goods[good_no] for good_no in goods.keys() \
                     if good_no not in good_busy_no and goods[good_no]['status'] == 0 } 
        
        #充电状态更新
        self.charge_plane()
         
        #安排飞机
        self.arrage_plane(good_idle,pos_enemy,time,pos_we)

        #已安排运输的货物被捡走了
        self.check_goods(pos_we,pos_enemy,goods)
            
        #空闲飞机占据了货物起点或终点，则挪动一个位置    
        self.move_plane(pos_we,goods)    
        #返回充电的飞机遇到停机坪上正在起飞的飞机，则提前等待
#        if 5 in self.busy.keys():                                                                                           
#            print('busy\n',self.busy[5])
#        if 5 in self.clear_plane.keys():
#            print('self.clear_plane\n',self.clear_plane[5])
        UAV_send = []
        charge = copy.deepcopy(self.charge)
        for UAV_no,UAV in charge.items(): 
            del UAV['type'],UAV['load_weight'],UAV['status']
            UAV_send.append(UAV)
        
        idle = copy.deepcopy(self.idle)
        for UAV_no,UAV in idle.items(): 
            del UAV['type'],UAV['load_weight'],UAV['status']
            UAV_send.append(UAV)
        
        clear = copy.deepcopy(self.clear_plane)
        for UAV_no,UAV in clear.items(): 
            if UAV_no not in self.busy.keys():
                if UAV["remain_electricity"] +self.prices[UAV['type']]['charge'] > self.prices[UAV['type']]['capacity']:
                    UAV["remain_electricity"] = self.prices[UAV['type']]['capacity']
                else:
                    UAV["remain_electricity"] += self.prices[UAV['type']]['charge']
                del UAV['type'],UAV['load_weight'],UAV['status']
                UAV_send.append(UAV)
        
        pos_we_next = []        
        for UAV,path,x,y,good_no in list(self.busy.values()):
            #计算剩余电量
            if UAV['goods_no'] >=0:
                UAV["remain_electricity"] -= goods[good_no]['weight']
            #格式化加入发送列表
            UAV_type = UAV['type']
            del UAV['type'],UAV['load_weight'],UAV['status']
            UAV_send.append(UAV)
            
            #该飞机飞到敌方可能相撞的位置，需要改变位置,只考虑可飞区域
            for plane_no,pos in nextpos_enemy.items():
                #充电飞机回去，被敌方飞机堵了
                if good_no == -2 and (UAV['x'], UAV['y'])!=self.parking and len(path)<=self.h_low+1:
                    if set(path)&set(pos) or set(path[1:])&set(pos_we) :
                        if path[-1]==(UAV['x'], UAV['y'], UAV['z']):
                            pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                            self.flag = 1
                            break
                        elif self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']-1) and (UAV['x'], UAV['y'],UAV['z']-1) != path[-1] \
                         and (UAV['x'], UAV['y'],UAV['z']-1) not in pos_we :
                            UAV['z'] -= 1
                            path.append((UAV['x'], UAV['y'], UAV['z']+1))
                            path.append((UAV['x'], UAV['y'], UAV['z']))
                            pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                            self.flag = 1
                            break
                        elif self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']+1) and (UAV['x'], UAV['y'],UAV['z']+1) != path[-1]:
                            UAV['z'] += 1                            
                            path.append((UAV['x'], UAV['y'], UAV['z']-1))
                            #保持一下，让另一架飞机飞过
                            path.append((UAV['x'], UAV['y'], UAV['z']))                           
                            pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                            self.flag = 1
                            break
                                  
                if path[-1] in pos and (UAV['x'], UAV['y'])!=self.parking:    
                    #我方有货物，且敌方位置不在货物终点
                    if UAV['goods_no']>=0 and (path[-1][0],path[-1][1]) != (goods[good_no]['end_x'], goods[good_no]['end_y']):
                        #敌方飞机是不动的,并且不在目的地上方
                        if pos[0]==pos[1] and path[-1][2]==self.h_low and UAV['z']==self.h_low and (path[-1][0],path[-1][1])!=self.parking and\
                        (path[-1][0],path[-1][1]) not in [(goods[good_no]['start_x'], goods[good_no]['start_y']),(goods[good_no]['end_x'], goods[good_no]['end_y'])]:
                            if (UAV['x'], UAV['y'],UAV['z']+1) != path[-1] and (UAV['x'], UAV['y'],UAV['z']-1) not in pos_we:
                                UAV['z'] += 1                                    
                                pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                                next_pos = path.pop()
                                path.append((path[-1][0], path[-1][1], UAV['z']))
                                path.append((next_pos[0], next_pos[1], UAV['z']))    
                                self.flag = 1
                                break
                        #敌方飞机是飞动的
                        elif pos[0]!=pos[1]:
                            if self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']-1) and (UAV['x'], UAV['y'],UAV['z']-1) != path[-1] \
                             and (UAV['x'], UAV['y'],UAV['z']-1) not in pos_we :
                                UAV['z'] -= 1
                                path.append((UAV['x'], UAV['y'], UAV['z']+1))
                                path.append((UAV['x'], UAV['y'], UAV['z']))
                                pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                                self.flag = 1
                                break
                            elif self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']+1) and (UAV['x'], UAV['y'],UAV['z']+1) != path[-1]:
                                UAV['z'] += 1                            
                                path.append((UAV['x'], UAV['y'], UAV['z']-1))
                                #保持一下，让另一架飞机飞过
                                path.append((UAV['x'], UAV['y'], UAV['z']))                           
                                pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                                self.flag = 1
                                break
                    #我方飞机无货物，并且飞机价值大于敌方
                    elif UAV['goods_no']<0 and self.prices[UAV_type]['value'] >= self.prices[self.pos_enemy[plane_no]['type']]['value'] and\
                        UAV_type!=self.chape_type:
                        #我方飞机刚放完货物，准备上升发现上方有敌方飞机
                        if UAV['z']<=self.h_low and UAV['z']+1==path[-1][2]:
                            if self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']-1) and (UAV['x'], UAV['y'],UAV['z']-1) != path[-1] \
                             and (UAV['x'], UAV['y'],UAV['z']-1) not in pos_we :
                                UAV['z'] -= 1
                                path.append((UAV['x'], UAV['y'], UAV['z']+1))
                                pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                                self.flag = 1
                                break
                        #敌方飞机是不动的
                        elif pos[0]==pos[1] and path[-1][2]==self.h_low and UAV['z']==self.h_low and (path[-1][0],path[-1][1])!=self.parking :
                            if (UAV['x'], UAV['y'],UAV['z']+1) != path[-1] and (UAV['x'], UAV['y'],UAV['z']-1) not in pos_we:
                                UAV['z'] += 1                                    
                                pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                                next_pos = path.pop()
                                path.append((path[-1][0], path[-1][1], UAV['z']))
                                path.append((next_pos[0], next_pos[1], UAV['z']))    
                                self.flag = 1
                                break
                        #敌方飞机是飞动的
                        elif pos[0]!=pos[1]:
                            if self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']-1) and (UAV['x'], UAV['y'],UAV['z']-1) != path[-1] \
                             and (UAV['x'], UAV['y'],UAV['z']-1) not in pos_we :
                                UAV['z'] -= 1
                                path.append((UAV['x'], UAV['y'], UAV['z']+1))
                                path.append((UAV['x'], UAV['y'], UAV['z']))
                                pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                                self.flag = 1
                                break
                            elif self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']+1) and (UAV['x'], UAV['y'],UAV['z']+1) != path[-1]:
                                UAV['z'] += 1                            
                                path.append((UAV['x'], UAV['y'], UAV['z']-1))
                                #保持一下，让另一架飞机飞过
                                path.append((UAV['x'], UAV['y'], UAV['z']))                           
                                pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                                self.flag = 1
                                break
                    
            if self.flag==1:
                self.flag = 0
                continue 
            
            #如果是驱逐机
            if good_no == -3:
                if (UAV['x'], UAV['y'], UAV['z']-1,-3) in pos_we_next:
                    pos_we_next.append((UAV['x'], UAV['y'], UAV['z'],-3))
                    continue    
                elif len(path)==1:                
                    (UAV['x'], UAV['y'], UAV['z']) = path[0]
                    pos_we_next.append((UAV['x'], UAV['y'], UAV['z'],-3)) 
                    continue
                elif path[-1] in pos_we_next:
                    if (UAV['x'], UAV['y'])==self.parking:
                        (UAV['x'], UAV['y'], UAV['z']) = path.pop()
                        pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                        continue
                    else:
                        if self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']-1) and (UAV['x'], UAV['y'],UAV['z']-1) != path[-1] \
                         and (UAV['x'], UAV['y'],UAV['z']-1) not in pos_we:
                            UAV['z'] -= 1
                            path.append((UAV['x'], UAV['y'], UAV['z']+1))
                            path.append((UAV['x'], UAV['y'], UAV['z']))
                            pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                            continue
                        elif self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']+1) and (UAV['x'], UAV['y'],UAV['z']+1) != path[-1]:
                            UAV['z'] += 1                            
                            path.append((UAV['x'], UAV['y'], UAV['z']-1))
                            #保持一下，让另一架飞机飞过
                            path.append((UAV['x'], UAV['y'], UAV['z']))                           
                            pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                            continue
                else:
                    (UAV['x'], UAV['y'], UAV['z']) = path.pop() 
                    pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                    continue
            else:
                #该飞机飞到我方可能相撞的位置，需要改变位置,只考虑可飞区域
                if path[-1] in pos_we_next:
                    if (UAV['x'], UAV['y'])==self.parking:
                        (UAV['x'], UAV['y'], UAV['z']) = path.pop()
                        pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                        continue
                    else:
                        if self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']-1) and (UAV['x'], UAV['y'],UAV['z']-1) != path[-1] \
                         and (UAV['x'], UAV['y'],UAV['z']-1) not in pos_we:
                            UAV['z'] -= 1
                            path.append((UAV['x'], UAV['y'], UAV['z']+1))
                            path.append((UAV['x'], UAV['y'], UAV['z']))
                            pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                            continue
                        elif self.is_valid_pos(UAV['x'], UAV['y'],UAV['z']+1) and (UAV['x'], UAV['y'],UAV['z']+1) != path[-1]:
                            UAV['z'] += 1                            
                            path.append((UAV['x'], UAV['y'], UAV['z']-1))
                            #保持一下，让另一架飞机飞过
                            path.append((UAV['x'], UAV['y'], UAV['z']))                           
                            pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
                            continue
                  
            
            #记录两个飞机相邻对向飞行
            pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))
            #记录交叉飞行会相撞的点
            if path[-1][0]!=UAV['x'] and path[-1][1]!=UAV['y']:
                pos_we_next.append((path[-1][0], UAV['y'], UAV['z']))
                pos_we_next.append((UAV['x'], path[-1][1], UAV['z']))
                
            #弹出下一步位置
            (UAV['x'], UAV['y'], UAV['z']) = path.pop() 
            #抓取货物
            if (UAV['x'], UAV['y'], UAV['z']) == (x,y,0) and good_no in goods.keys() and UAV['goods_no']!=good_no:
                UAV['goods_no']=good_no                      
                UAV["remain_electricity"] -= goods[good_no]['weight']
        
            if not len(path):
                if (UAV['x'], UAV['y']) == self.parking and good_no==-2:
                    if UAV["remain_electricity"] +self.prices[UAV_type]['charge'] > self.prices[UAV_type]['capacity']:
                        UAV["remain_electricity"] = self.prices[UAV_type]['capacity']
                    else:
                        UAV["remain_electricity"] += self.prices[UAV_type]['charge']
                    self.charge[UAV['no']] = UAV
                else:
                    self.idle[UAV['no']] = UAV
                del self.busy[UAV['no']]
            #记录之前无人机下一步飞行点，则下一架飞机不得走这些点
            pos_we_next.append((UAV['x'], UAV['y'], UAV['z']))           
                
        #购买更新无人机                        
        buy = self.buy_plane(data['we_value'])
        
        return UAV_send,buy 
    
    def arrage_plane(self,good_idle,pos_enemy,time,pos_we):   
        #优先安排驱逐机
        for UAV_no,UAV in self.clear_plane.items():
            if (UAV['x'], UAV['y']) == self.parking and self.down_plane() and \
            (not (set((UAV['x'], UAV['y'],i) for i in range(1,self.h_low+1)) & set(pos_enemy)) or\
             (set((UAV['x'], UAV['y'],i) for i in range(1,self.h_low+1)) & set(pos_we))):
                continue
            if UAV_no not in self.busy.keys(): 
                #如果敌方飞机坪上方没我方飞机
                s_hight,e_hight = 0,0#self.safe
                c_x, c_y, c_z = self.parking[0], self.parking[1], self.h_low
                s_x, s_y, s_z = self.enPaking[0],self.enPaking[1], self.h_low
                path = self.path_find(c_x, c_y, c_z, s_x, s_y, s_z,s_hight,e_hight)[1:] 
                self.busy[UAV_no]=(UAV,path, self.enPaking[0],self.enPaking[1],-3)
                return
               
         #空闲飞机按可载重大小排序（升序）        
        UAV_idle_sorted = sorted(self.idle.items(),key = lambda x:x[1]['load_weight'])
        #货物按价值高低排序（降序）
        good_idle_sorted = sorted(good_idle.items(),key = lambda x:x[1]['value'],reverse = True)
        
        for UAV_no,UAV in UAV_idle_sorted:            
            #选择没有安排飞机运送的货物
            for good_no,good in good_idle_sorted:            
#                #排除不正常货物
#                if self.map[good['start_x'],good['start_y'],0] != 'x':
                #该货物上方没有敌方飞机准备运送，且可被我方飞机载起
                if UAV['load_weight'] >= good['weight'] and not (set((good['start_x'],good['start_y'],i) for i in range(self.h_low)) & set(pos_enemy)):
                    #起飞高度
                    s_hight = UAV['z']
                    #停止高度
                    e_hight = 0
                    c_x, c_y, c_z = UAV['x'], UAV['y'], self.h_low
                    s_x, s_y, s_z = good['start_x'], good['start_y'], self.h_low
                    e_x, e_y, e_z = good['end_x'], good['end_y'], self.h_low                                                 
                    #计算无人机到货物的路径 
                    path = self.path_find(c_x, c_y, c_z, s_x, s_y, s_z,s_hight,e_hight)                        
                    # 如果到货物的路径长度小于货物存在时间，则计算运输路径
                    if path and len(path) < good['remain_time'] + good['start_time'] - time: 
                        s_hight,e_hight = 0,self.safe
#                        e_hight = self.safe
                        #计算货物到目的地的路径    
                        path_good = self.path_find(s_x, s_y, s_z, e_x, e_y, e_z,s_hight,e_hight)
                        #判断现有电量是否可运输
                        if (len(path_good)-self.safe)*good['weight'] < UAV["remain_electricity"]:
                            if (UAV['x'], UAV['y']) == self.parking and (self.down_plane() or\
                                (set((UAV['x'], UAV['y'],i) for i in range(1,self.h_low+1)) & set(pos_enemy))):
                                break
                            path = path_good + path
                            #飞机从空闲列表删除加入到忙列表中,包括飞机信息，运送路径，货物所在地点以及货物编号
                            self.busy[UAV_no]=(UAV,path, s_x, s_y,good_no)
                            good_idle_sorted.remove((good_no,good))
                            del self.idle[UAV_no]
                            if (UAV['x'], UAV['y']) == self.parking :
                                self.flag = 1  
                            #有合适的货物则不返回充电
                            if self.charge_flag:
                                self.charge_flag = 0
                            break
                           
                        elif (UAV['x'], UAV['y']) != self.parking and UAV["remain_electricity"] < self.prices[UAV['type']]['capacity']:
                        #现有电量不能运输，则返回充电,充电标志置高
                            self.charge_flag = 1
            #遍历所有货物仍需要充电               
            if self.charge_flag and not (set((self.parking[0],self.parking[1],i) for i in range(1,self.h_low)) & set(pos_we)):
                s_hight,e_hight = UAV['z'],0
                path = self.path_find(UAV['x'], UAV['y'], self.h_low, self.parking[0], self.parking[1], self.h_low,s_hight,e_hight)   
                self.busy[UAV_no]=(UAV,path,self.parking[0],self.parking[1],-2)
                del self.idle[UAV_no]
            self.charge_flag = 0
            #若已进行过一次路径规划，则终止
            if self.flag:
                self.flag = 0
                return
            
    def down_plane(self):
        for UAV,path,x,y,good_no in list(self.busy.values()):
            if good_no == -2 and len(path)<= (2*self.h_low+1):
                return True
        return False
    
    def move_plane(self,pos_we,goods):
        #空闲飞机占据了货物起点或终点，则挪动一个位置
        idle_temp = copy.deepcopy(self.idle)
        good_pos = [(good['end_x'], good['end_y']) for good in goods.values()] \
                 + [(good['start_x'], good['start_y']) for good in goods.values()]                 
        for UAV_no, UAV in idle_temp.items():
            #空闲飞机占据了货物起点或终点，则挪动一个位置                
            if (UAV['x'],UAV['y']) in good_pos:
                path = []
                for x, y in zip(self.xs1,self.ys1):
                    if self.is_valid_pos(UAV['x']+x,UAV['y']+y,0) and (UAV['x'], UAV['y'],self.safe) not in pos_we:
                        for i in range(self.safe,self.h_low):
                            path.append((UAV['x']+x,UAV['y']+y,i))
                        for i in range(self.h_low,UAV['z'],-1):
                            path.append((UAV['x'],UAV['y'],i))
                        self.busy[UAV_no] = (UAV,path,-1,-1,-1)                        
                        del self.idle[UAV_no]
                        break
    
    def check_goods(self,pos_we,pos_enemy,goods):
        #已安排运输的货物被捡走了 
        for UAV,path,x,y,good_no in self.busy.values():             
            #货物消失
            if good_no not in goods.keys() and good_no>=0 and UAV['z'] >= self.h_low: 
                if (UAV['x'], UAV['y'],self.safe) not in pos_we:
                    #就地降落修改路径
                    if self.map[UAV['x'], UAV['y'],0]!= 'x' and (UAV['x'], UAV['y']) != self.parking:
                        path = [(UAV['x'], UAV['y'],i) for i in range(self.safe,UAV['z'])]
                        self.busy[UAV['no']]= (UAV,path,-1,-1,-1)
                        break
            #若货物正上方有敌方飞机开始下降取货或未取货上升
            if good_no in goods.keys():
                good = goods[good_no]                    
                pos = (set((good['start_x'],good['start_y'],i) for i in range(self.h_low)) & set(pos_enemy))
                if (pos and pos.pop()[2] < UAV['z']) or good['status'] == 1:                          
                    #确认不是我方飞机捡走的                           
                    if UAV['goods_no']!= good['no'] and (UAV['x'], UAV['y'],self.safe) not in pos_we:
                        if (good['start_x'],good['start_y']) != (UAV['x'], UAV['y'])and UAV['z']>= self.h_low: 
                            #就地降落修改路径
                            if self.map[UAV['x'], UAV['y'],0]!= 'x' and (UAV['x'], UAV['y']) != self.parking:
                                path = [(UAV['x'], UAV['y'],i) for i in range(self.safe,UAV['z'])]
                                self.busy[UAV['no']]= (UAV,path,-1,-1,-1)        
                        else:
                            if UAV['z'] < self.h_low:
                                if good['value'] > self.prices[UAV['type']]['value']//2:continue
                                for x, y in zip(self.xs1,self.ys1):
                                    if self.is_valid_pos(UAV['x']+x,UAV['y']+y,0) and (UAV['x'], UAV['y'],self.safe) not in pos_we:
                                        path = []
                                        #下降的时候才看到敌军
                                        for i in range(self.safe,self.h_low+1):
                                            path.append((UAV['x']+x,UAV['y']+y,i))
                                        for i in range(self.h_low,UAV['z'],-1):
                                            path.append((UAV['x'],UAV['y'],i))
                                        self.busy[UAV['no']] = (UAV,path,-1,-1,-1)                        
                                        break
    
    def update_enemy(self,UAV_enemy):
        UAV_enemy = {plane['no']:plane for plane in UAV_enemy if plane['status'] == 0}
        nextpos_enemy = {}
        for plane_no, plane in UAV_enemy.items():
            if plane_no in self.pos_enemy.keys():
                #记录敌机下一步位置
                nextpos_enemy[plane_no] = [(2*plane['x']-self.pos_enemy[plane_no]['x'],2*plane['y']-self.pos_enemy[plane_no]['y'],2*plane['z']-self.pos_enemy[plane_no]['z'])]
                #记录敌机当前位置
                nextpos_enemy[plane_no].append((plane['x'],plane['y'],plane['z']))
                #如果敌机对角飞行，记录对角两边的位置
                if plane['x']- self.pos_enemy[plane_no]['x'] and plane['y']-self.pos_enemy[plane_no]['y']:
                    nextpos_enemy[plane_no].append((2*plane['x']-self.pos_enemy[plane_no]['x'],plane['y'],plane['z']))
                    nextpos_enemy[plane_no].append((plane['x'],2*plane['y']-self.pos_enemy[plane_no]['y'],plane['z']))
        self.pos_enemy = UAV_enemy
        #记录已下降敌机的位置
        pos_enemy = list(map(lambda plane:(plane['x'],plane['y'],plane['z']) if plane['z'] < self.h_low else None,UAV_enemy.values()))
        return nextpos_enemy,pos_enemy
    
    def update_plane(self,UAV_we):
        #统计我方飞机位置
        pos_we = []
        #更新所有飞机字典
        for UAV in UAV_we:
            #飞机坠毁,从忙字典或空闲字典删除
            if UAV['status'] == 1:
                if UAV['no'] in self.busy.keys():
                    if UAV['no'] in self.clear_plane.keys():
                        del self.clear_plane[UAV['no']]
                        #从忙列表删除
                        del self.busy[UAV['no']] 
                    else:
                        del self.busy[UAV['no']]
                    #从现有飞机中删除
                        self.type[UAV['type']].remove(UAV['no'])     
                elif UAV['no'] in self.idle.keys():
                    #从空闲字典删除
                    del self.idle[UAV['no']]
                    #从现有飞机中删除
                    self.type[UAV['type']].remove(UAV['no'])           
                continue
            #飞机在充电
            elif UAV['no'] in self.charge.keys():
                self.charge[UAV['no']] = UAV
                continue
            #飞机在空闲字典里
            elif UAV['no'] in self.idle.keys():
                #记录位置
                self.idle[UAV['no']] = UAV
                pos_we.append((UAV['x'],UAV['y'],UAV['z']))
                continue
            #飞机在忙字典里
            elif UAV['no'] in self.busy.keys():
                self.busy[UAV['no']] = (UAV,self.busy[UAV['no']][1],self.busy[UAV['no']][2],self.busy[UAV['no']][3],self.busy[UAV['no']][4])             
                #记录位置
                pos_we.append((UAV['x'],UAV['y'],UAV['z']))
                continue
            elif UAV['no'] in self.clear_plane.keys():
                self.clear_plane[UAV['no']] = UAV
                continue
            #飞机不在现有飞机字典里，加入现有飞机字典，加入充电字典
            elif UAV['type'] ==self.chape_type and len(self.clear_plane)<self.clear_num:
                self.clear_plane[UAV['no']] = UAV
                continue
            elif UAV['no'] not in self.type[UAV['type']]:  
                self.type[UAV['type']].append(UAV['no'])
                self.charge[UAV['no']] = UAV
                continue        
        return pos_we
    
    def charge_plane(self):
        #实现飞机充电功能
        charge = copy.deepcopy(self.charge)
        for no, UAV in charge.items():
            #充电满，加入空闲表
            if UAV["remain_electricity"] == self.prices[UAV['type']]['capacity']:
                self.idle[no] = UAV
                del self.charge[no]
            elif UAV["remain_electricity"] +self.prices[UAV['type']]['charge'] > self.prices[UAV['type']]['capacity']:
                self.charge[no]["remain_electricity"] = self.prices[UAV['type']]['capacity']
            else:
                self.charge[no]["remain_electricity"] += self.prices[UAV['type']]['charge']
            
    
    def buy_plane(self,we_value):
        #购买更新无人机，策略：
        buy = []
        for i in range(round((self.clear_num-len(self.clear_plane))/2)):
            if we_value >= self.prices[self.chape_type]['value']:
                buy.append({ "purchase": self.chape_type })
                we_value -= self.prices[self.chape_type]['value']
                
        for t,no in self.type.items():
            if len(no) < self.prices[t]['num']:
                if we_value >= self.prices[t]['value']:
                    buy.append({ "purchase": t })
                    we_value -= self.prices[t]['value']
        return buy                
        
    def cluNum(self,price):
        weight = [p['load_weight'] for p in price]
        weight.sort()
        if len(weight)>=3:
            weight = weight[1:-1]
        else:
            weight = weight[:-1]
    
        buyNum = []
    
        for i in range(len(weight)):
            if i ==0:
                buyNum.append(weight[i]-10)
            else:
                buyNum.append(weight[i]-weight[i-1])
        num={}
        for i in range(len(weight)):
            num[weight[i]]=max(1,round(buyNum[i]*self.flaneNum/sum(buyNum)))
        for p in self.prices.values():
            for w in num.keys():
                if p['load_weight']== w:
                    p['num']=num[w]
                    break
                else:
                    p['num']=1
    
    def is_valid_coord(self, x, y, z):  
        if x < 0 or x >= self.length or y < 0 or y >= self.width or z < self.h_low or z > self.h_high :  
            return False  
        return self.map[x,y,z] != 'x'
    
    def is_valid_pos(self, x, y, z):  
        if x < 0 or x >= self.length or y < 0 or y >= self.width or z < 0 or z > self.h_high:  
            return False  
        return self.map[x,y,z] != 'x'
    
    def heuristic(self,a, b):
        #曼哈顿距离
        re = abs(b[0] - a[0]) + abs(b[1] - a[1]) + abs(b[2]-a[2])
        return re
        
    def path_find(self,s_x, s_y, s_z, e_x, e_y, e_z,s_hight,e_hight):
        start = (s_x, s_y, s_z)
        goal = (e_x, e_y, e_z)
        close_set = set()
        came_from = {}
        gscore = {start:0}
        fscore = {start:self.heuristic(start,goal)* 10}
    
        pqueue = []
    
        heapq.heappush(pqueue, (fscore[start],start))  
        
        xs = (-1, 0, 1, -1, 1, -1, 0, 1, 0, 0)  
        ys = (-1,-1,-1,  0, 0,  1, 1, 1, 0, 0)
        zs = ( 0, 0, 0,  0, 0,  0, 0, 0, 1,-1)
        
        while pqueue:
            #选取代价最小的点
            current = heapq.heappop(pqueue)[1]
            #与前一个点的交集格子最大有4个
            pqueue = heapq.nsmallest(4, pqueue)            
            if current == goal:
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                #添加飞机高度到可飞高度间的路径
                for i in range(s_z,s_hight,-1):
                    path.append((s_x, s_y,i))
                l = []
                for i in range(e_hight,0,-1):
                    l.append((e_x, e_y,i))
                for i in range(e_z):
                    l.append((e_x, e_y,i))
                path =  l + path
                return path                  
    
            close_set.add(current)
            
            for x, y, z in zip(xs, ys,zs):
                
                if not self.is_valid_coord(current[0]+x,current[1]+y,current[2]+z):
                    continue
    
                neighbour = current[0]+x,current[1]+y,current[2]+z
                
                tentative_g_score = gscore[current] + 1                    
                
                if neighbour in close_set: #and tentative_g_score >= gscore.get(neighbour,0):
                    continue
                    
                if  (tentative_g_score < gscore.get(neighbour,0) or
                     neighbour not in [i[1]for i in pqueue]):
                    came_from[neighbour] = current
                    gscore[neighbour] = tentative_g_score
                    fscore[neighbour] = tentative_g_score + self.heuristic(neighbour,goal) * 10
                    heapq.heappush(pqueue, (fscore[neighbour], neighbour))
        return []
