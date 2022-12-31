from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
from torch.utils.data import DataLoader
import math
import random
from torch.optim.lr_scheduler import CosineAnnealingLR
from matplotlib import pyplot as plt
import pandas as pd
from typing import Any, cast, Dict, List, Optional, Union
import numpy as np

def set_seed(seed):
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True

def conv_init(in_channels, out_channels, kernel_size=3, stride=1,padding=1, bias=False, args=None, ):
    layer = ConvMerge(in_channels, out_channels, kernel_size, stride=stride,padding=padding, bias=bias)
    layer.init(args)
    return layer

class ConvMerge(nn.Conv2d):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.weight_align = None

    def init(self, args):
        self.args = args

        set_seed(self.args.weight_seed)

        # this isn't default initialization.  not sure if necessary, need to test.
        if self.args.kn_init:
            nn.init.kaiming_normal_(self.weight, mode="fan_in", nonlinearity="relu")
        # models do NOT need to be initialized the same, however they appeared to converge slightly faster with same init
        # self.args.weight_seed+=1

    def forward(self, x):
        x = F.conv2d(
            x, self.weight, self.bias, stride=self.stride, padding=self.padding, dilation=self.dilation, groups=self.groups
        )
        weights_diff = torch.tensor(0)
        if self.weight_align is not None:
            # using absolute error here.
            if self.args.align_loss=='ae':
                weights_diff = torch.sum((self.weight - self.weight_align).abs())
            elif self.args.align_loss=='se':
                weights_diff=torch.mean((self.weight-self.weight_align)**2)
        return x, weights_diff


def linear_init(in_dim, out_dim, bias=False, args=None, ):
    layer = LinearMerge(in_dim, out_dim, bias=bias)
    layer.init(args)
    return layer


class LinearMerge(nn.Linear):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.weight_align = None

    def init(self, args):
        self.args = args
        set_seed(self.args.weight_seed)
        # this isn't default initialization.  not sure if necessary, need to test.
        if self.args.kn_init:
            nn.init.kaiming_normal_(self.weight, mode="fan_in", nonlinearity="relu")
        # models do NOT need to be initialized the same, however they appeared to converge slightly faster with same init

    def forward(self, x):
        x = F.linear(x, self.weight, self.bias)
        weights_diff = torch.tensor(0)
        if self.weight_align is not None:

            if self.args.align_loss=='ae':
                weights_diff = torch.sum((self.weight - self.weight_align).abs())
            elif self.args.align_loss=='se':
                weights_diff=torch.mean((self.weight-self.weight_align)**2)
        return x, weights_diff

class Conv4(nn.Module):
    def __init__(
        self,  args=None, weight_merge=False ) -> None:
        super().__init__()

        self.bias=True
        self.args=args
        self.weight_merge=weight_merge

        if self.weight_merge:
            self.conv1 = conv_init(3, 64, args=self.args)
            self.conv2 = conv_init(64, 64, args=self.args)
            self.conv3 = conv_init(64, 128, args=self.args)
            self.conv4 = conv_init(128, 128, args=self.args)
            self.fc1=linear_init(32*32*8, 256, args=self.args)
            self.fc2=linear_init(256, 256, args=self.args)
            self.fc3=linear_init(256, 10, args=self.args)
        else:

            self.conv1 = nn.Conv2d(3, 64, kernel_size=3, padding=1, bias=self.bias)
            self.conv2 = nn.Conv2d(64, 64, kernel_size=3, padding=1, bias=self.bias)
            self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1, bias=self.bias)
            self.conv4 = nn.Conv2d(128, 128, kernel_size=3, padding=1, bias=self.bias)
            self.fc1=nn.Linear(32*32*8, 256, bias=self.bias)
            self.fc2=nn.Linear(256, 256, bias=self.bias)
            self.fc3=nn.Linear(256, 10, bias=self.bias)

        self.max_pool=nn.MaxPool2d((2, 2))
        self.relu=nn.ReLU(True)
        #self.avgpool = nn.AdaptiveAvgPool2d((7, 7))




    def forward(self, x: torch.Tensor) -> torch.Tensor:

        if self.weight_merge:
            x,wd1 = self.conv1(x)
            x = self.relu(x)
            x,wd2 = self.conv2(x)
            x = self.relu(x)
            x = self.max_pool(x)
            x,wd3 = self.conv3(x)
            x = self.relu(x)
            x,wd4 = self.conv4(x)
            x = self.relu(x)
            x = self.max_pool(x)
            x = x.view(x.size(0), 8192)
            x,wd5 = self.fc1(x)
            x = self.relu(x)
            x,wd6 = self.fc2(x)
            x = self.relu(x)
            x,wd7 = self.fc3(x)
            wd=wd1+wd2+wd3+wd4+wd5+wd6+wd7
            return x, wd
        else:
            x=self.conv1(x)
            x=self.relu(x)
            x=self.conv2(x)
            x=self.relu(x)
            x=self.max_pool(x)
            x=self.conv3(x)
            x=self.relu(x)
            x=self.conv4(x)
            x=self.relu(x)

            x=self.max_pool(x)
            x = x.view(x.size(0), 8192)
            x = self.fc1(x)

            x = self.relu(x)
            x = self.fc2(x)
            x = self.relu(x)
            x = self.fc3(x)
            return x, torch.tensor(0)





#model = VGG(make_layers(cfgs["A"], batch_norm=False), )



def get_datasets(args):
    # not using normalization
    #transform = transforms.Compose([
        #transforms.ToTensor(),
    #])
    normalize = transforms.Normalize(
        mean=[0.491, 0.482, 0.447], std=[0.247, 0.243, 0.262]
    )

    test_transform = transforms.Compose(
        [
            transforms.ToTensor(),
            normalize,
        ]
    )
    if args.data_transform:
        train_transform = transforms.Compose(
            [
                transforms.RandomCrop(32, padding=4),
                transforms.RandomHorizontalFlip(),
                transforms.ToTensor(),
                normalize,
            ]
        )
    else:
        train_transform=test_transform
    if args.baseline:
        dataset1 = datasets.CIFAR10(f'{args.base_dir}data', train=True, download=True, transform=train_transform)
        test_dataset = datasets.CIFAR10(f'{args.base_dir}data', train=False, transform=test_transform)
        train_loader = DataLoader(dataset1, batch_size=args.batch_size, shuffle=True)
        test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)
        return train_loader, test_loader
    else:
        dataset1 = datasets.CIFAR10(f'{args.base_dir}data', train=True, download=True, transform=train_transform)
        dataset2 = datasets.CIFAR10(f'{args.base_dir}data', train=True, transform=train_transform)
        # split dataset in half by labels
        labels = np.unique(dataset1.targets)
        ds1_labels = labels[:len(labels) // 2]
        ds2_labels = labels[len(labels) // 2:]
        print(f'ds1_labels: {ds1_labels}')
        print(f'ds2_labels: {ds2_labels}')
        ds1_indices = [idx for idx, target in enumerate(dataset1.targets) if target in ds1_labels]
        ds2_indices = [idx for idx, target in enumerate(dataset1.targets) if target in ds2_labels]
        '''
        #use this code for p/1-p split.  need to test
        #p=0.8
        ds1_indices=ds1_indices[:int(len(ds1_indices)*p)]+ds2_indices[int(len(ds2_indices)*p):]
        ds2_indices=ds1_indices[int(len(ds1_indices)*p):]+ds2_indices[:int(len(ds2_indices)*p)]
        '''

        '''
        #use this code to split dataset down middle. need to test
        dataset1.data, dataset1.targets = dataset1.data[:int(len(dataset1.targets)/2)], dataset1.targets[:int(len(dataset1.targets)/2)]
        dataset2.data, dataset2.targets = dataset2.data[int(len(dataset1.targets)/2):], dataset2.targets[int(len(dataset1.targets)/2):]
        '''

        dataset1.data,dataset1.targets = dataset1.data[ds1_indices],list(np.array(dataset1.targets)[ds1_indices])
        dataset2.data, dataset2.targets = dataset2.data[ds2_indices], list(np.array(dataset2.targets)[ds2_indices])
        assert (set(ds1_indices).isdisjoint(ds2_indices))

        test_dataset = datasets.CIFAR10(f'{args.base_dir}data', train=False, transform=test_transform)
        train_loader1 = DataLoader(dataset1, batch_size=args.batch_size, shuffle=True)
        train_loader2 = DataLoader(dataset2, batch_size=args.batch_size, shuffle=True)
        test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)
        return train_loader1, train_loader2, test_loader


class Trainer:
    def __init__(self, args, datasets, model, device, save_path, model_name):
        self.args = args
        self.model = model
        self.train_loader, self.test_loader = datasets[0], datasets[1]
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.args.lr)
        self.criterion = nn.CrossEntropyLoss(reduction='sum')
        self.device = device
        self.save_path = save_path
        self.model_name = model_name

        self.fc1_norm_list = []
        self.fc2_norm_list = []
        self.wa1_norm_list = []
        self.wa2_norm_list = []
        self.train_iter_list=[]
        self.train_iter=0

    def fit(self, log_output=False):
        self.train_iter+=1
        for epoch in range(1, self.args.epochs + 1):
            self.train()
            test_loss, test_acc = self.test()
            self.test_loss = test_loss
            self.test_acc = test_acc

            #if epoch_loss < self.train_loss:
                #torch.save(self.model.state_dict(), self.save_path)
            if log_output:
                print( f'Epoch: {epoch}, Train loss: {self.train_loss}, Test loss: {self.test_loss}, Test Acc: {self.test_acc}')

    def model_loss(self):
        return self.best_loss

    def train(self, ):
        self.model.train()
        train_loss_ce=0
        train_loss=0

        for batch_idx, (data, target) in enumerate(self.train_loader):

            data, target = data.to(self.device), target.to(self.device)
            self.optimizer.zero_grad()
            output, weight_align = self.model(data)
            '''
            weight_align_factor=250 works for this particular combination, summing both CrossEntropyLoss and weight alignment
            For model w/o weight alignment paramter, second part of loss is 0  
            '''
            loss = self.criterion(output, target) + self.args.weight_align_factor * weight_align
            train_loss += loss
            train_loss_ce += self.criterion(output, target)
            loss.backward()
            self.optimizer.step()

        self.train_loss_ce=train_loss_ce/len(self.train_loader.dataset)
        self.train_loss= train_loss / len(self.train_loader.dataset)

    def test(self, ):
        self.model.eval()
        test_loss = 0
        correct = 0

        with torch.no_grad():
            for data, target in self.test_loader:
                data, target = data.to(self.device), target.to(self.device)
                output, sd = self.model(data, )
                test_loss += self.criterion(output, target).item()
                pred = output.argmax(dim=1, keepdim=True)
                correct += pred.eq(target.view_as(pred)).sum().item()
        test_loss /= len(self.test_loader.dataset)
        return test_loss, 100. * correct / len(self.test_loader.dataset)


def set_weight_align_param(model1, model2, args):
    for model1_mods, model2_mods, in zip(model1.named_modules(), model2.named_modules(),):
        n1, m1 = model1_mods
        n2, m2 = model2_mods
        if not type(m2) == LinearMerge and not type(m2)==ConvMerge:
            continue
        if hasattr(m1, "weight"):
            '''
            m1.weight gets updated to m2.weight_align because it is not detached.  and vice versa
            This is a simple way to "share" the weights between models. 
            Alternatively we could set m1.weight=m2.weight_align after merge model is done training.  
            '''
            # We only want to merge one models weights in this file
            # m1.weight_align=nn.Parameter(m2.weight, requires_grad=True)s
            m2.weight_align = nn.Parameter(m1.weight, requires_grad=True)
            m1.weight_align = nn.Parameter(m2.weight, requires_grad=True)

class Merge_Iterator:
    def __init__(self, args, datasets, device, weight_dir):

        self.args = args
        self.device = device
        self.weight_dir = weight_dir
        self.train_loader1 = datasets[0]
        self.train_loader2 = datasets[1]
        self.test_dataset = datasets[2]

    def train_single(self, model, save_path, train_dataset, model_name):
        '''
        ****** We need to initialize a new optimizer during each iteration.
        Not sure why, but this is the only way it works.
        '''
        trainer = Trainer(self.args, [train_dataset, self.test_dataset], model, self.device, save_path, model_name)
        trainer.fit()
        return trainer

    def run(self):
        merge_iterations = self.args.merge_iter
        #intra_merge_iterations=[10 for i in range(2)]+[5 for i in range(2)]+[2 for i in range(10)]+[1 for i in range(10000)]

        model1 = Conv4(self.args, weight_merge=True).to(self.device)
        model2 = Conv4(self.args, weight_merge=True).to(self.device)

        model1_trainer = Trainer(self.args, [self.train_loader1, self.test_dataset], model1, self.device,
                                 f'{self.weight_dir}model1_0.pt', 'model1_double')
        model2_trainer = Trainer(self.args, [self.train_loader2, self.test_dataset], model2, self.device,
                                 f'{self.weight_dir}model2_0.pt', 'model2_double')

        '''
        AdaDelta works with re-initialization (because of the adadptive state)
        SGD works with one initialization, but requires tuning the weight_align_factor and learning rate.
        model1_trainer.optimizer = optim.SGD(model1.parameters(), lr=self.args.lr)
        model2_trainer.optimizer = optim.SGD(model2.parameters(), lr=self.args.lr)
        '''
        lr_schedule = [self.args.lr for i in range(int(self.args.merge_iter*0.5))] + \
                      [self.args.lr*.1 for i in range(int(self.args.merge_iter*0.25))]   + \
                      [self.args.lr*.01 for i in range(int(self.args.merge_iter*0.25))]
        for iter in range(merge_iterations):

            model1_trainer.optimizer=optim.Adam(model1.parameters(), lr=lr_schedule[iter])
            model2_trainer.optimizer=optim.Adam(model2.parameters(), lr=lr_schedule[iter])

            #print(f'Inter Merge Iterations: {intra_merge_iterations[iter]}')
            for iter2 in range(1):
            #for iter2 in range(intra_merge_iterations[iter]):
                model1_trainer.fit()
                model2_trainer.fit()

            if iter==0:
                set_weight_align_param(model1, model2, self.args)

            print(f'Merge Iteration: {iter} \n'
                  f'\tModel 1 Train loss: {model1_trainer.train_loss}, Train CE loss: {model1_trainer.train_loss_ce}, Test loss: {model1_trainer.test_loss},  Test accuracy: {model1_trainer.test_acc}\n'
                  f'\tModel 2 Train loss: {model2_trainer.train_loss}, Train CE loss: {model1_trainer.train_loss_ce}, Test loss: {model2_trainer.test_loss},  Test accuracy: {model2_trainer.test_acc}')


def main():
    # Training settings
    parser = argparse.ArgumentParser(description='PyTorch Weight Align')
    parser.add_argument('--batch-size', type=int, default=256,
                        help='input batch size for training (default: 64)')
    parser.add_argument('--epochs', type=int, default=1,
                        help='number of epochs to train')
    parser.add_argument('--merge_iter', type=int, default=20000,
                        help='number of iterations to merge')
    parser.add_argument('--data_transform', type=bool, default=False)
    parser.add_argument('--kn_init', type=bool, default=False)
    parser.add_argument('--align_loss', type=str, default=None)
    parser.add_argument('--weight_align_factor', type=int, default=250, )
    parser.add_argument('--lr', type=float, default=1e-3, metavar='LR',
                        help='learning rate (default: 1.0)')
    parser.add_argument('--gamma', type=float, default=0.7,
                        help='Learning rate step gamma (default: 0.7)')
    parser.add_argument('--seed', type=int, default=1, metavar='S',
                        help='random seed (default: 1)')
    parser.add_argument('--weight_seed', type=int, default=1, )
    parser.add_argument('--gpu', type=int, default=1, )
    parser.add_argument('--save-model', action='store_true', default=False,
                        help='For Saving the current Model')
    parser.add_argument('--baseline', type=bool, default=False, help='train base model')
    parser.add_argument('--graphs', type=bool, default=False, help='add norm graphs during training')
    parser.add_argument('--base_dir', type=str, default="/s/luffy/b/nobackup/mgorb/",
                        help='Directory for data and weights')
    args = parser.parse_args()
    set_seed(args.seed)
    device = torch.device(f"cuda:{args.gpu}" if torch.cuda.is_available() else "cpu")
    print(f'Using Device {device}')

    weight_dir = f'{args.base_dir}iwa_weights/'
    if args.baseline:
        train_loader1, test_dataset = get_datasets(args)
        model = Conv4(args, weight_merge=False).to(device)

        model_parameters = filter(lambda p: p.requires_grad, model.parameters())
        params = sum([np.prod(p.size()) for p in model_parameters])
        print(params)

        save_path = f'{weight_dir}cifar10_baseline.pt'
        trainer = Trainer(args, [train_loader1, test_dataset], model, device, save_path, 'model_baseline')
        trainer.fit(log_output=True)
    else:
        train_loader1, train_loader2, test_dataset = get_datasets(args)
        merge_iterator = Merge_Iterator(args, [train_loader1, train_loader2, test_dataset], device, weight_dir)
        merge_iterator.run()


if __name__ == '__main__':
    main()