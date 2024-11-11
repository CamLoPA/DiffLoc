import csitool.csitools as csitools
import numpy as np
from csitool.passband import lowpass
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from csitool.read_pcap import NEXBeamformReader
from scipy.fft import fft, fftfreq
from CSIKit.reader import get_reader

def smooth_data(data, window_size=35):
    return np.convolve(data, np.ones(window_size)/window_size, mode='same')

# 计算一阶导数
def derivative(data):
    return np.diff(data)

def find_main_frequency(signal, sampling_rate):
    # 计算快速傅里叶变换（FFT）
    fft_values = fft(signal)
    
    # 计算对应的频率
    fft_frequencies = fftfreq(len(signal), 1 / sampling_rate)
    
    # 提取有意义的频率和FFT值（通常是正频率部分）
    positive_freq_indices = np.where(fft_frequencies >= 0)
    fft_frequencies = fft_frequencies[positive_freq_indices]
    fft_values = np.abs(fft_values[positive_freq_indices])
    
    # 找到幅度最大的频率
    main_frequency = fft_frequencies[np.argmax(fft_values)]
    
    return main_frequency

def find_wave_indices(data):
    smoothed_data = smooth_data(data)
    first_derivative = derivative(smoothed_data)
    
    # 找到最高波峰的索引
    peak_index = np.argmax(data)

    mean_data = np.mean(data)
    
    # 从波峰向前搜索波的开始索引
    start_index = peak_index
    damax = data[peak_index]
    #while data[start_index] >= 1.05*mean_data and start_index > 0:
    while data[start_index]>np.max(data[int(len(data)/20):int(start_index-len(data)/15)]) and start_index > len(data)/15-1:
      while np.max(data[int(start_index-len(data)/15):start_index]) > 0.4*(np.mean(data[int(start_index-len(data)/15):start_index]) + damax) and start_index > len(data)/15-1:
        while start_index > len(data)/15-1 and first_derivative[start_index - 1] > 0:
              start_index -= 1
        start_index -= 1
      start_index -= 1
    dastart = data[start_index]
    # 从波峰向后搜索波的结束索引
    end_index = peak_index
    while data[end_index] > 0.4*(dastart + damax) or np.max(data[end_index:int(end_index+len(data)/10)]) > 0.7*damax and end_index < len(first_derivative)-1:
      while end_index < len(first_derivative)-1 and first_derivative[end_index] < 0:
          end_index += 1
      end_index += 1

    start_var = np.var(data[int(start_index-len(data)/10):start_index])
    start_max = np.max(data[int(start_index-len(data)/10):start_index]) - np.min(data[int(start_index-len(data)/10):start_index])

    if end_index + len(data)/10 < len(data):
      end_var = np.var(data[end_index:int(end_index+len(data)/10)])
      end_max = np.max(data[end_index:int(end_index+len(data)/10)]) - np.min(data[end_index:int(end_index+len(data)/10)])
    else:
      end_var = np.var(data[end_index:len(data)])
      end_max = np.max(data[end_index:len(data)]) - np.min(data[end_index:len(data)])

    start_mean = np.mean(data[0:start_index])

    if end_index + start_index < len(data):
      end_mean = np.mean(data[len(data)-start_index:len(data)])
    else:
      end_mean = np.mean(data[len(data)-start_index:len(data)])

    if len(data)-peak_index<2*len(data)/10:
       if np.var(data[int(len(data)/10):int(2*len(data)/5)])<1.2*np.var(data[int(3*len(data)/5):int(9*len(data)/10)]):
        return True, 0, 100
       else:
        return False, 0, 100
       
    if len(data)-end_index<1.5*len(data)/10 and end_index-start_index > 0.4*len(data):
       if np.var(data[int(len(data)/10):int(2*len(data)/5)])<1.2*np.var(data[int(3*len(data)/5):int(9*len(data)/10)]):
        return True, 0, 100
       else:
        return False, 0, 100

    if start_mean - end_mean > 35:
      if np.var(data[start_index:end_index])/0.5*(np.var(data[int(start_index-len(data)/10):start_index])+np.var(data[end_index:int(end_index+len(data)/10)]))<5:
          return False, 0, 100
      else:
          return False, start_index, end_index
    elif end_mean - start_mean > 35:
      if np.var(data[start_index:end_index])/0.5*(np.var(data[int(start_index-len(data)/10):start_index])+np.var(data[end_index:int(end_index+len(data)/10)]))<5:
          return True, 0, 100
      else:
          return True, start_index, end_index
    else:
      if start_var>end_var:
        if np.var(data[end_index:int(2*end_index-start_index)]) < 0:
          return True, 0, 100
        if np.var(data[start_index:end_index])/0.5*(np.var(data[int(start_index-len(data)/5):start_index])+np.var(data[end_index:int(end_index+len(data)/5)]))<5:
          return True, 0, 100
        else:
          return True, start_index, end_index
      elif start_var>0.4*end_var and start_max>=0.85*end_max:
        if np.var(data[end_index:int(2*end_index-start_index)]) < 2:
          return True, 0, 100
        if np.var(data[start_index:end_index])/0.5*(np.var(data[int(start_index-len(data)/5):start_index])+np.var(data[end_index:int(end_index+len(data)/5)]))<5:
          return True, 0, 100
        else:
          return True, start_index, end_index
      else:
        if np.var(data[start_index:end_index])/0.5*(np.var(data[int(start_index-len(data)/10):start_index])+np.var(data[end_index:int(end_index+len(data)/10)]))<5:
          return False, 0, 100
        else:
          return False, start_index, end_index

def moving_average(data, window_size):
    return np.convolve(data, np.ones(window_size) / window_size, mode='valid')

def moving_variance(data, window_size):
    mean = moving_average(data, window_size)
    return moving_average((data[window_size-1:] - mean) ** 2, window_size)

def detect_transition(data, window_size=30, threshold=70):
    mean = moving_average(data, window_size)
    variance = moving_variance(data, window_size)
    plt.plot(variance)
    plt.show()
    
    transition_start = None
    transition_end = None

    for i in range(len(variance)):
        if variance[i] > threshold and transition_start is None:
            transition_start = i
        if variance[i] < threshold and transition_start is not None:
            if len(data) - i >150:
              if transition_start>150:
                if np.mean(data[i:i+150]) <= np.mean(data[transition_start-150:transition_start])-0.1*abs(np.mean(data[transition_start-150:transition_start])):
                    transition_end = i
                    break
                else:
                   continue
              else:
                if np.mean(data[i:i+150]) <= np.mean(data[0:transition_start])-0.1*abs(np.mean(data[0:transition_start])):
                    transition_end = i
                    break
                else:
                   continue
            else:
              if transition_start>150:
                    if np.mean(data[i:len(data)]) < np.mean(data[transition_start-150:transition_start])-0.1*abs(np.mean(data[transition_start-150:transition_start])):
                        transition_end = i
                        break
                    else:
                      continue
              else:
                if np.mean(data[i:len(data)]) < np.mean(data[0:transition_start])-0.1*abs(np.mean(data[0:transition_start])):
                    transition_end = i
                    break
                else:
                  continue
    transition_end = i

    return transition_start, transition_end

def cumulative_mean(data):
    # 计算累积和
    cumsum = np.cumsum(data)
    
    # 计算均值
    cumulative_mean = cumsum / np.arange(1, len(data) + 1)
    
    return cumulative_mean

def calculate_transition_indices(data, window_size=50, threshold_ratio=10):
    transition_start, transition_end = None, None
    data = moving_average(data, window_size)
    if np.mean(data[0:int(len(data)/2)]) > np.mean(data[int(len(data)/2):len(data)]):
      for i in range(int(len(data)/10),len(data)):
        if np.mean(data[0:i]) > np.mean(data[i:len(data)]):
           continue
        else:
           transition_start = transition_end = i
           break
    else:
       print(np.mean(data[0:2*int(len(data)/5)]))
       print(np.mean(data[int(2*len(data)/5):len(data)]))
       print(np.mean(data))
       for i in range(int(len(data)/10),len(data)):
        if np.mean(data[0:i]) < np.mean(data):
          continue
        else:
          transition_start = transition_end = i
          break

    return transition_start, transition_end

def find_best_t(data):
    n = len(data)
    front_mean = np.mean(data[n * 1 // 5:n * 2 // 5])
    back_mean = np.mean(data[-n * 2 // 5:-n * 1 // 5])
    
    best_t = 0
    min_difference = float('inf')
    
    for t in range(1, n):
        constructed_data = np.concatenate([
            np.full(t, front_mean),
            np.full(n - t, back_mean)
        ])
        
        difference = np.linalg.norm(data[0:n] - constructed_data)
        
        if difference < min_difference:
            min_difference = difference
            best_t = t
    print(t)
    return best_t, front_mean, back_mean

def find_special_points(data):
    data = smooth_data(data)
    n = len(data)
    t, front_mean, back_mean = find_best_t(data)
    if front_mean > back_mean:
        tf = t
        while data[tf] < front_mean:
          tf = tf-1
        pre_t_point = tf
        if t < len(data):
          while data[t] > 0.9*back_mean and t<len(data):
            t = t+1
        post_t_point = t
    else:
        tf = t
        while data[tf] > front_mean:
          tf = tf-1
        pre_t_point = tf
        while data[t] < 0.9*back_mean:
          t = t+1
        post_t_point = t
    if abs(np.mean(data[int(1*n/10):pre_t_point]) - np.mean(data[post_t_point:int(9*n/10)]))<10:
        return int(0), int(0.75*len(data))
    else:
      return pre_t_point, post_t_point

def remove_data_with_high_variance(data):
    data = np.array(data)
    
    for i in range(len(data) - 2, -1, -1):
        variance = np.var(data[i:])
        
        if variance > 1:
            return data[0:i]
            break

datapath = r'D:\cam\ys3-28.61-2capture_1.pcap'
'''my_reader = get_reader(datapath)
csi_data = my_reader.read_file(datapath,scaled=True)'''
my_reader = NEXBeamformReader()
csi_data = my_reader.read_file(datapath,scaled=True)
csi_matrix, no_frames, no_subcarriers = csitools.get_CSI(csi_data)
csi_matrix_first = csi_matrix[:, :, 0, 0]
csi_matrix_first[csi_matrix_first == -np.inf] = np.nan
imp_mean = SimpleImputer(missing_values=np.nan, strategy='mean')
csi_matrix_first = imp_mean.fit_transform(csi_matrix_first)
# Then we'll squeeze it to remove the singleton dimensions.
csi_matrix_squeezed = np.squeeze(csi_matrix_first)
csi_matrix_squeezed = np.transpose(csi_matrix_squeezed)
for x in range(no_subcarriers-1):
  csi_matrix_squeezed[x] = lowpass(csi_matrix_squeezed[x], 3, 50, 5)
  #csi_matrix_squeezed[x] = hampel(csi_matrix_squeezed[x], 10, 3)
  #csi_matrix_squeezed[x] = running_mean(csi_matrix_squeezed[x], 10)

csi_matrix_squeezed = np.transpose(csi_matrix_squeezed)
pca = PCA(n_components=3)
csipca = pca.fit_transform(csi_matrix_squeezed)
csipca = np.transpose(csipca)
csipca0 = remove_data_with_high_variance(csipca[0])
x = csi_data.timestamps
x = csi_data.timestamps - x[0]
csi_matrix_squeezed = np.transpose(csi_matrix_squeezed)
csi_mean = 0-np.mean(csi_matrix_squeezed,axis=0)
plt.plot(csipca0)
plt.show()
for i in range(no_subcarriers-1):
  plt.plot(csi_matrix_squeezed[i])
plt.show()
plt.plot(csi_mean)
plt.show()
ispostive, start_index,  end_index = find_wave_indices(csi_mean)
print(f"Postive: {ispostive}, Start Index: {start_index}, End Index: {end_index}")
print(f"Postive: {ispostive}, Start Index: {x[start_index]}, End Index: {x[end_index]}")
'''start_index, end_index = find_special_points(csipca0)
print(f"Start Index: {start_index}, End Index: {end_index}")
print(f"Start Index: {x[start_index]}, End Index: {x[end_index]}")'''
'''csi_matrix_squeezed = np.transpose(csi_matrix_squeezed)
BatchGraph.plot_heatmap(csi_matrix_squeezed, csi_data.timestamps)'''