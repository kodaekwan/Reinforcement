import gym
import time
import random
import numpy as np
import math
import matplotlib
import matplotlib.pyplot as plt
from collections import namedtuple
from itertools import count
from PIL import Image

import torch
import torch.nn.functional as F
import torchvision.transforms as T
import cv2

class Episode_Threshold():#random Threshold
    def __init__(self,EPS_START = 0.9,EPS_END = 0.05,EPS_DECAY = 200):
        self.EPS_START=EPS_START;
        self.EPS_END=EPS_END;
        self.EPS_DECAY=EPS_DECAY;
        self.step=0;
    def get_threshold(self):
        eps_threshold = self.EPS_END+ (self.EPS_START-self.EPS_END)*math.exp(-1. * self.step / self.EPS_DECAY);
        self.step+=1;
        return eps_threshold;


class Model(torch.nn.Module):
    def __init__(self,height,width,output_size):
        super(Model,self).__init__();

        self.conv1 = torch.nn.Conv2d(3,16,kernel_size=5,stride=2);
        self.bn1 = torch.nn.BatchNorm2d(16);
        self.conv2 = torch.nn.Conv2d(16,32,kernel_size=5,stride=2);
        self.bn2 = torch.nn.BatchNorm2d(32);
        self.conv3 = torch.nn.Conv2d(32,32,kernel_size=5,stride=2);
        self.bn3 = torch.nn.BatchNorm2d(32);
        
        def conv2d_size_out(size, kernel_size=5, stride = 2):
            return ((size - (kernel_size-1)-1) // stride) + 1;

        convw = conv2d_size_out(conv2d_size_out(conv2d_size_out(width)));
        convh = conv2d_size_out(conv2d_size_out(conv2d_size_out(height)));
        linear_input_size = convw * convh * 32;

        self.head = torch.nn.Linear(linear_input_size,output_size);

    def forward(self,x):
        # if height = 40, width= 90, output_size = 2
        x = F.relu(self.bn1(self.conv1(x)));#(batch,16,40,90)->(batch,16,18,43)
        x = F.relu(self.bn2(self.conv2(x)));#(batch,16,18,43)->(batch,32,7,20)
        x = F.relu(self.bn3(self.conv3(x)));#(batch,32,7,20)->(batch,32,2,8)
        return self.head(x.view(x.size(0),-1));#(batch,32,2,8)-> (batch,32*2*8) -> (batch,2)



class GAME():
    def __init__(self,game_name='CartPole-v0'):
        self.env = gym.make(game_name);# make game
        self.reset();
        
    def get_cart_location(self,image_width):
        # you can get cart position from pixel unit
        # env.state[0] is cart position
        world_width = self.env.x_threshold * 2;
        scale = image_width/world_width;
        return int(self.env.state[0]*scale + image_width/2.0);
    
    def reset(self):
        self.env.reset();
        image_shape = self.get_screen().shape;
        self.max_key_num = self.env.action_space.n;
        self.image_height = image_shape[0];
        self.image_width = image_shape[1];
        self.image_channel = image_shape[2];
        self.cart_location=self.get_cart_location(self.image_width);
    
    def get_screen(self):
        return self.env.render(mode='rgb_array');
    
    def set_control(self,key):
        return self.env.step(key);

    def close(self):
        self.env.close();
    
    def cut_image(self,src,x=0,y=0,width=600,height=400):
        #src (H,W,C)
        return src[y:y+height,x:x+width:];
    
    def focus_cut_image(self,src,focus=(0,1),width=600,height=400):
        # "src" is numpy type and have shape to (H,W,C)
        # "focus" is (x,y)
        # "width" is cutting range from "focus x"
        # "height" is cutting range from "focus y".
        screen_shape=src.shape;
        
        screen_height=screen_shape[0];
        screen_width=screen_shape[1];

        if focus[0] < width//2:
            w_slice_range = slice(0,width)
        elif focus[0] > (screen_width - (width//2) ):
            w_slice_range = slice(-width,None);
        else:
            w_slice_range = slice((focus[0]-(width//2)), (focus[0]+(width//2)));
        
        if focus[1] < height//2:
            h_slice_range = slice(0,height)
        elif focus[1] > (screen_height - (height//2) ):
            h_slice_range = slice(-height,None);
        else:
            h_slice_range = slice((focus[1]-(height//2)), (focus[1]+(height//2)));

        return src[h_slice_range,w_slice_range,:];
    
    def resize_image(self,src,width,height):
        return cv2.resize(src, dsize=(width, height), interpolation=cv2.INTER_CUBIC);

class Reinforcement_learnig():
    def __init__(self,policy_net=None,target_net=None,device=None):
        if(device==None):
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu");
        else:
            self.device=device;
        if(policy_net!=None):
            self.policy_net=policy_net.to(self.device);
        if(target_net!=None):
            self.target_net=target_net.to(self.device);
        self.Threshold = Episode_Threshold(EPS_START=0.9,EPS_END=0.05,EPS_DECAY=200);
    
    def get_policy_action(self,state,action_num=2):
        # state is network 1 batch input data
        sample = random.random();
        if (sample>self.Threshold.get_threshold()):
            with torch.no_grad():# don't update 
                output  = self.policy_net(state);
                # max(1) mean data get maximun value based 1 dimension tensor.
                # .max(1) same method => np.argmax(output,axis=1)
                # if a=[[1,2],[3,4],[5,6]], np.argmax(a,axis=1)  = [ 2 , 4 , 6 ];
                index_output=output.max(1)[1];
                # max_value,max_value_index=output.max(1);
                # output.max(1) return tensor[ max value, index of max value]; => example a=tensor[[1,2],[3,4],[6,1]], a.max(1) = tensor[[ 2 , 4 , 6 ], [ 1 , 1 , 0 ]]
                # output.max(1)[1] is index => example a=tensor[[1,2],[3,4],[6,1]], a.max(1) = [[ 2 , 4 , 6 ], [ 1 , 1 , 0 ] ], a.max(1)[1] = [1,1,0]
                return index_output.view(1,1);
        else:
            return torch.tensor([[random.randrange(action_num)]],device=self.device,dtype=torch.long);
            
    

game=GAME();
image_height=game.image_height;
image_width=game.image_width;
image_channel=game.image_channel;
max_action_num=game.max_key_num;

print("image height : ",image_height);
print("image width : ",image_width);
print("image channel : ",image_channel);
print("game action number : ",max_action_num);

image_focus=(game.cart_location,int(image_height*0.6));
image_cut_width = int(image_width*0.6);
image_cut_height = int(image_height*0.4);


device = torch.device("cuda" if torch.cuda.is_available() else "cpu");
policy_net=Model(height=40,width=90,output_size=2);
RL=Reinforcement_learnig(policy_net=policy_net,target_net=None,device=device);


#get image and cut, resize
now_screen = game.get_screen();
now_screen=game.focus_cut_image(src=now_screen,focus=image_focus,width=image_cut_width,height=image_cut_height);
now_screen=game.resize_image(now_screen,90,40);# get now state for image

privous_screen = now_screen;
different_screen = now_screen-privous_screen;#calculate different screen

# image transform from numpy to torch tensor
float_dsc=np.array([different_screen],dtype=np.float32)/255.0;# RGB image(0~255) -> RGB image(0.0~1.0)
float_dsc=float_dsc.transpose((0,3,1,2));# (Batch, Height, Width, Channel)->(Batch, Channel, Height, Width)
tensor_dsc=torch.from_numpy(float_dsc);# numpy image -> tensor image
tensor_dsc=tensor_dsc.to(device);# cpu -> gpu

#get state before action
now_state = tensor_dsc; # we define that now_state is different screen before action.

for _  in range(100):

    # Decide action from policy network 
    action=RL.get_policy_action(state=now_state,action_num=2);
    action_cpu = action.item();# gpu -> cpu

    # Execute action in Game environment by network policy
    observation,reward,done,info = game.set_control(action_cpu);
    
    # if done game 
    if(done==True):
        print(observation)
        print("done")
        game.reset();
        image_focus=(game.cart_location,int(game.image_height*0.6));
        break;

    #!!get current image after action from Game environment!!
    now_screen = game.get_screen();
    plt.imshow(now_screen,interpolation='none');

    # current image cut and resize
    now_screen=game.focus_cut_image(src=now_screen,focus=image_focus,width=image_cut_width,height=image_cut_height);
    now_screen=game.resize_image(now_screen,90,40);# get now state for image
    
    # calculate next_state after action
    different_screen = now_screen-privous_screen;#calculate different screen
    float_dsc=np.array([different_screen],dtype=np.float32)/255.0;# RGB image(0~255) -> RGB image(0.0~1.0)
    float_dsc=float_dsc.transpose((0,3,1,2));# (Batch, Height, Width, Channel)->(Batch, Channel, Height, Width)
    tensor_dsc=torch.from_numpy(float_dsc);# numpy image -> tensor image
    tensor_dsc=tensor_dsc.to(device);# tensor position move from cpu to gpu
    next_state = tensor_dsc; # we define that next_state is different screen after action.

    plt.imshow(different_screen,interpolation='none');
    plt.pause(0.01);

    # !!!recoding results!!!
    [now_state,action,next_state,reward];

    # change from now data to previous data by time flow.
    now_state = next_state;
    privous_screen = now_screen;
    
game.close();
plt.close();
exit();
