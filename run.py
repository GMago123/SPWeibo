import torch
import torch.nn as nn
import random
import numpy as np
import logging
import argparse
import time
import os
import pandas as pd
import urllib
from tqdm import tqdm
import matplotlib.pyplot as plt

from train import getTrain
from utils import getTime
from data import getData
from model import getModel
from config import Config


def setup_seed(seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.backends.cudnn.deterministic = True

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--modelName', type=str, default='spwrnn_beta',
                        help='spwrnn/rnn/tcn/spwrnn_wo_l/spwrnn_beta')    
    parser.add_argument('--dataset', type=str, default='renminribao',
                        help='weibo dataset name')  
    parser.add_argument('--model_save_dir', type=str, default='results/models',
                        help='path to save results.')
    parser.add_argument('--res_save_dir', type=str, default='results/results',
                        help='path to save results.')
    parser.add_argument('--device', type=int, default=0,
                        help='GPU id.')
    parser.add_argument('--tune', type=bool, default=False,
                        help='True if run tune task.')
    parser.add_argument('--infer', type=bool, default=False,
                        help='True if run infer task.')
    parser.add_argument('--load', type=str, default='results/models/regression_0/spwrnn_beta.pth',
                        help='model to be loaded in infer task.')
    parser.add_argument('--log_order', type=int, default=0,
                        help='set log file order and model file order.')
    parser.add_argument('--csv_order', type=int, default=0,
                        help='set result csv file order.')
    parser.add_argument('--interval', type=int, default=None,
                        help='repost observation cycle (seconds). preconfig.')
    parser.add_argument('--constant_framing', type=int, default=None,
                        help='if use constant framing in dataset. preconfig. 1=True 0=False')
    return parser.parse_args()


def run(args, config):
    if not os.path.exists(args.model_save_dir):
        os.makedirs(args.model_save_dir)
    args.model_save_path = os.path.join(args.model_save_dir,
                                        f'{args.modelName}.pth')
    dataset_ = getData(args.modelName)(args=args, config=config)
    model_to_be_init = getModel(modelName=args.modelName)
    model = model_to_be_init(config=config, args=args).to(args.device)
    train_to_be_init = getTrain(modelName=args.modelName)
    train = train_to_be_init(args=args, config=config)
    train_loader, val_loader, test_loader = dataset_.get_train_val_dataloader()
    # do train
    best_score = train.do_train(model=model, train_dataloader=train_loader, val_dataloader=val_loader)
    # save result
    logging.info(getTime() + '本次最优结果：%.4f' % best_score)

    model.load_state_dict(torch.load(args.model_save_path))
    test_results, pred, true = train.do_test(model=model, dataloader=test_loader, mode="TEST")

    return test_results

def run_eval(args, config):
    # model settings
    config.use_predicted_framing=False
    dataset_ = getData(args.modelName)(args=args, config=config)
    # model_to_be_init = getModel(modelName=args.modelName)
    # model = model_to_be_init(config=config, args=args).to(args.device)
    # model.load_state_dict(torch.load(args.load))
    # train_to_be_init = getTrain(modelName=args.modelName)
    # train = train_to_be_init(args=args, config=config)

    # framing analysis
    original_data = dataset_.get_data()
    # [text, processed_time_series, publish_time(seconds in a day), topic embedding, framing]
    framing_cls = {}
    framing_num = {}
    for i in range(len(original_data)):
        framing = original_data[i][4]
        key = ''.join([str(item) for item in list(framing)])
        if key in framing_cls:
            framing_cls[key].append(original_data[i][1])
        else:
            framing_cls[key] = [ original_data[i][1] ]
    framing_cls_avg_repost = {}
    for key in framing_cls:
        framing_num[key] = len(framing_cls[key])
        framing_cls_avg_repost[key] = np.mean(framing_cls[key], axis=0)

    # # infer
    # framing_cls_avg_repost_counter_facts = {}
    # num = 0
    # for key in framing_cls_avg_repost:
    #     num += 1
    #     print(f"{num} counter fact experiment.")
    #     framing_decode = np.array([eval(i) for i in key])
    #     # set samples to fixed framing.
    #     for i in range(len(original_data)):
    #         original_data[i][4] = framing_decode

    #     # predict the counter fact result.
    #     preds = []
    #     train_loader, val_loader, test_loader = dataset_.get_train_val_dataloader(data=original_data)
    #     for dataloader in [train_loader, val_loader, test_loader]:
    #         pred = train.do_infer(model, dataloader)
    #         preds.append(pred)
    #     preds = np.concatenate(preds, axis=0)
    #     framing_cls_avg_repost_counter_facts[key] = np.mean(preds, axis=0)

    # draw results
    save_dir = os.path.join(args.res_save_dir, 'figures')
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    for idx, key in enumerate(['100000', '010000', '001000', '000100', '000010', '000001', '000000', '011000', '001001']):
        repost_num = np.e ** framing_cls_avg_repost[key] - 1
        repost_num = np.concatenate([[0], repost_num])
        # repost_num_counter_fact = np.e ** framing_cls_avg_repost_counter_facts[key] - 1
        x_label = np.arange(0.0, 24.5, 0.5)
        plt.clf()
        plt.plot(x_label, repost_num, color='red', marker='o',linestyle='dotted')
        plt.annotate("%.1f" % repost_num[-1], (x_label[-1], repost_num[-1]-2))
        plt.xlim(0, 24)
        plt.ylim(bottom=0)
        plt.xlabel("hours")
        plt.ylabel("cumulative repost number")
        plt.title("Framing code:" + key + f", count:{framing_num[key]}")
        plt.savefig(os.path.join(save_dir, f"{idx}.png"), dpi=200)
        # plt.clf()
        # plt.plot(x_label, repost_num_counter_fact, color='green', marker='v',linestyle='--')
        # plt.annotate("%.1f" % repost_num_counter_fact[-1], (x_label[-1], repost_num_counter_fact[-1]-2))
        # plt.xlabel("hours")
        # plt.ylabel("repost number")
        # plt.title(key + " counter_fact")
        # plt.savefig(os.path.join(save_dir, key + "_counter_fact.png"))
    return None


def run_task(args, seeds, config):
    logging.info('************************************************************')
    logging.info(getTime() + '本轮参数：' + str(config))
    logging.info(getTime() + '本轮Args：' + str(args))

    original_result = {}

    for seed in seeds:
        setup_seed(seed)
        # 每个种子训练开始
        logging.info(getTime() + 'Seed：%d 训练开始' % seed)      
        current_res = run(args, config)
        if not original_result:
            for key in current_res:
                original_result[key] = [current_res[key]]
        else:
            for key in current_res:
                original_result[key].append(current_res[key])

    # 保存实验结果
    result = {}
    for key in original_result:            
        mean, std = round(np.mean(original_result[key]), 3), round(np.std(original_result[key]), 3)
        result[key] = str(mean)
        result[key + '-std'] = str(std)
    for key in config:
        result[key] = config[key]
    result['Args'] = args
    result['Config'] = config

    logging.info('本轮效果均值：%s, 标准差：%s' % (result[config.KeyEval], result[config.KeyEval + '-std']))

    mode = "tune" if args.tune else "single"
    save_path = os.path.join(args.res_save_dir, f'{args.modelName}-{args.dataset}-{mode}-{args.csv_order}.csv')
    if not os.path.exists(args.res_save_dir):
        os.makedirs(args.res_save_dir)
    if os.path.exists(save_path):
        df = pd.read_csv(save_path)
        columns = set(df.columns)
        if set(result.keys()) == columns:       # 如果与已检测到的结果文件格式相符，直接保存
            df = df.append(result, ignore_index=True)
        else:  # 如果格式不符，另存一个文件
            for key in result:
                result[key] = [result[key]]
            df = pd.DataFrame(result)
            save_path = save_path[:-4] + "new.csv" 
            logging.info('Warning: 结果格式不符，另存一个新文件.')
    else:       # 不存在结果，新建文件
        for key in result:
            result[key] = [result[key]]
        df = pd.DataFrame(result)
   
    df.to_csv(save_path, index=None)
    logging.info('Results are added to %s...' % (save_path))
    logging.info('************************************************************')


def run_tune(args, preconfig, seeds, tune_times=50):
    has_debuged = []
    tune_number = 0
    while tune_number < tune_times:
        logging.info('-----------------------------------Tune(%d/%d)----------------------------' % (tune_number+1, tune_times))
        # 加载之前的结果参数以去重
        save_path = os.path.join(args.res_save_dir, f'{args.modelName}-{args.dataset}-tune-{args.csv_order}.csv')
        if os.path.exists(save_path):
            df = pd.read_csv(save_path)
            for j in range(len(df)):
                has_debuged.append(df.loc[j, "Config"])

        setup_seed(int(time.time()))              # 随机选取种子以初始化随机的config
        config = Config(args.modelName, args.dataset, tune=True, preconfig=preconfig).get_config()

        if str(config) in has_debuged:
            logging.info(getTime() + '该参数已经被搜索过.')
            time.sleep(1.)
            continue

        # run_task(args=args, seeds=seeds, config=config)
        # has_debuged.append(str(config))
        # tune_number += 1
        try:
            run_task(args=args, seeds=seeds, config=config)
            has_debuged.append(str(config))
            tune_number += 1
        except Exception as e:
            logging.info(getTime() + '运行时发生错误. ' + str(e))


if __name__ == '__main__':
    args = parse_args()
    ## load some config from args
    preset_config = {}
    if args.interval:
        preset_config['interval'] = args.interval
    if args.constant_framing:
        preset_config['constant_framing'] = False if args.constant_framing == 0 else True
    if not os.path.exists('log'):
        os.makedirs('log')
    file_name = f'log/{args.modelName}_tune_{args.log_order}.log' if args.tune else f'log/{args.modelName}_reg_{args.log_order}.log'
    logging.basicConfig(filename=file_name, level=logging.INFO)
    args.device = 'cuda:'+ str(args.device)
    if args.infer:
        configure = Config(modelName=args.modelName, dataset=args.dataset, preconfig=preset_config).get_config()
        run_eval(args=args, config=configure)
    elif not args.tune:
        args.model_save_dir = os.path.join(args.model_save_dir, f'regression_{args.log_order}')
        configure = Config(modelName=args.modelName, dataset=args.dataset, preconfig=preset_config).get_config()
        run_task(args=args, seeds=[111], config=configure)
    else:
        args.model_save_dir = os.path.join(args.model_save_dir, f'tune_{args.log_order}')
        run_tune(args=args, preconfig=preset_config, seeds=[111], tune_times=100)

