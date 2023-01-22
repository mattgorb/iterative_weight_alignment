from torchvision import datasets, transforms
from torch.utils.data import DataLoader
import numpy as np
import collections

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
        num_clients = args.num_clients
        dataset1 = datasets.CIFAR10(f'{args.base_dir}data', train=True, download=True, transform=train_transform)

        train_loaders = []
        if args.disjoint_classes:
            assert num_clients in [2, 5, 10]

            if num_clients == 2:
                labels_iter = [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]
            elif num_clients == 5:
                labels_iter = [[0, 1], [2, 3], [4, 5], [6, 7], [8, 9]]
            elif num_clients == 10:
                labels_iter = [[0], [1], [2], [3], [4], [5], [6], [7], [8], [9]]

            print(f'label groupings: {labels_iter}')

            index_groupings = []
            for label_list in labels_iter:
                index_group = [idx for idx, target in enumerate(dataset1.targets) if target in label_list]
                index_groupings.append(index_group)
            if args.imbalanced:
                if num_clients != 2:
                    print('Clients needs to be 2')
                    sys.exit()
                # use this code for p/1-p split.  need to test
                p = 0.8
                d1 = index_groupings[0][:int(len(index_groupings[0]) * p)] + index_groupings[1][
                                                                             int(len(index_groupings[1]) * p):]
                d2 = index_groupings[0][int(len(index_groupings[0]) * p):] + index_groupings[1][
                                                                             :int(len(index_groupings[1]) * p)]

                dataset1 = datasets.CIFAR10(f'{args.base_dir}data', train=True, transform=train_transform)
                dataset2 = datasets.CIFAR10(f'{args.base_dir}data', train=True, transform=train_transform)

                dataset1.data, dataset1.targets = dataset1.data[d1], np.array(dataset1.targets)[d1]
                dataset2.data, dataset2.targets = dataset2.data[d2], np.array(dataset1.targets)[d2]
                assert (set(d1).isdisjoint(d2))
                train_loader1 = DataLoader(dataset1, batch_size=args.batch_size, shuffle=True)
                train_loader2 = DataLoader(dataset2, batch_size=args.batch_size, shuffle=True)
                train_loaders.append(train_loader1)
                train_loaders.append(train_loader2)
            else:
                for group in index_groupings:
                    dataset = datasets.CIFAR10(f'{args.base_dir}data', train=True, transform=train_transform)
                    dataset.data, dataset.targets = dataset.data[group], np.array(dataset1.targets)[group]
                    train_loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)
                    train_loaders.append(train_loader)
                if num_clients == 2:
                    assert (set(index_groupings[0]).isdisjoint(index_groupings[1]))
                else:
                    # random assertions
                    assert (set(index_groupings[0]).isdisjoint(index_groupings[1]))
                    assert (set(index_groupings[0]).isdisjoint(index_groupings[2]))
                    assert (set(index_groupings[1]).isdisjoint(index_groupings[2]))
                    assert (set(index_groupings[1]).isdisjoint(index_groupings[3]))
                    assert (set(index_groupings[3]).isdisjoint(index_groupings[4]))


        else:
            num_clients = args.num_clients
            lst = np.arange(len(dataset1))
            random.shuffle(lst)
            for group in np.array_split(lst, num_clients):
                dataset = datasets.CIFAR10(f'{args.base_dir}data', train=True, transform=train_transform)
                dataset.data, dataset.targets = dataset.data[group], np.array(dataset1.targets)[group]
                train_loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)
                train_loaders.append(train_loader)

        test_dataset = datasets.CIFAR10(f'{args.base_dir}data', train=False, transform=test_transform)
        test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)

        print('Dataset summaries:')

        for i in range(len(train_loaders)):
            print(
                f'Train set {i}: Length: {len(train_loaders[i].dataset)}, Labels: {collections.Counter(train_loaders[i].dataset.targets.tolist())}')

        print(
            f'Test set: Length: {len(test_loader.dataset)}, Labels: {collections.Counter(test_loader.dataset.targets.tolist())}')
        return train_loaders, test_loader

