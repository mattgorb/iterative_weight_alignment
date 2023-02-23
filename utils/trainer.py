from __future__ import print_function
import argparse
import torch
import torch.nn as nn

import torch.optim as optim


class Trainer:
    def __init__(self, args, datasets, model, device, model_name):
        self.args = args
        self.model = model
        self.train_loader, self.test_loader = datasets[0], datasets[1]

        self.optimizer = optim.Adam(self.model.parameters(), lr=self.args.lr)


        #self.optimizer = optim.SGD(self.model.parameters(), lr=0.05,  weight_decay=1e-3)
        #self.scheduler = torch.optim.lr_scheduler.StepLR(self.optimizer, step_size=1, gamma=.998)


        self.criterion = nn.CrossEntropyLoss(reduction='sum')
        self.device = device


        self.fc1_norm_list = []
        self.fc2_norm_list = []
        self.wa1_norm_list = []
        self.wa2_norm_list = []
        self.train_iter_list=[]
        self.train_iter=0

        self.weight_dir = f'{self.args.base_dir}iwa_weights/'

        self.model_name = model_name
        self.save_path=f'{self.weight_dir}{self.model_name}.pt'

    def fit(self, log_output=True):
        self.train_iter+=1
        if self.train_iter>0:
            checkpoint = torch.load(self.save_path)
            self.optimizer = optim.Adam(self.model.parameters(), lr=self.args.lr)
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            #self.optimizer = optim.SGD(self.model.parameters(), lr=0.1*(0.998**self.train_iter), weight_decay=1e-3)
            #self.scheduler = torch.optim.lr_scheduler.StepLR(self.optimizer, step_size=1, gamma=.998)

        for epoch in range(1, self.args.local_epochs + 1):
            self.train()

            test_loss, test_acc = self.test()
            self.test_loss = test_loss
            self.test_acc = test_acc

            #self.scheduler.step()

            if log_output:
                print( f'Local Epoch: {epoch}, Train loss: {self.train_loss}, Test loss: {self.test_loss}, Test Acc: {self.test_acc}')

        torch.save({
            'epoch': self.train_iter,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict()
        }, self.save_path)

        self.optimizer.zero_grad()
        del self.optimizer
        torch.cuda.empty_cache()



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


            loss = self.criterion(output, target) + self.args.weight_align_factor * weight_align
            loss.backward()

            #torch.nn.utils.clip_grad_norm_(parameters=self.model.parameters(),  max_norm=10)  # Clip gradients to prevent exploding
            self.optimizer.step()

            train_loss += loss.item()
            train_loss_ce += self.criterion(output, target).item()

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
