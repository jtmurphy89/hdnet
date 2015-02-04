# -*- coding: utf-8 -*-
"""
    hdnet.spikes
    ~~~~~~~~~~~~

    Spikes class handling multi-neuron , multi-trial spike trains.

    :copyright: Copyright 2014 the authors, see AUTHORS.
    :license: GPLv3, see LICENSE for details.
"""

__version__ = "0.1"

import os
import numpy as np
from util import hdlog, Restoreable
from visualization import save_matrix_whole_canvas


class Spikes(Restoreable, object):
    """ Class for handling binary time-series datasets

    Parameters
        npz_file: filename of N x M numpy array containing M time bin steps of N neurons' spikes
                        OR T x N x M numpy array of T trials, repeated stimulus
        spikes_arr:  T x N x M array of spikes (T always present even when T = 1)

        preprocess: makes data into binary {0,1} (Heaviside)
                    override for other operations on raw data
    """
    _SAVE_ATTRIBUTES_V1 = ['_spikes_arr', '_T', '_N', '_M']
    _SAVE_VERSION = 1
    _SAVE_TYPE = 'Spikes'

    # factory

    @classmethod
    def from_spikes_array(cls, spikes_arr, bin_size=1, preprocess=True, **kwargs):
        return cls(spikes_arr=spikes_arr, bin_size=bin_size, preprocess=preprocess, **kwargs)

    @classmethod
    def from_npz_file(cls, npz_file, bin_size=1, preprocess=True, **kwargs):
        return cls(npz_file=npz_file, bin_size=bin_size, preprocess=preprocess, **kwargs)

    @classmethod
    def from_mat_file(cls, mat_file, bin_size=1, preprocess=True, **kwargs):
        return cls(mat_file=mat_file, bin_size=bin_size, preprocess=preprocess, **kwargs)

    @classmethod
    def from_spk_files(cls, spk_files, bin_size=1, preprocess=True, **kwargs):
        return cls(spk_files=spk_files, bin_size=bin_size, preprocess=preprocess, **kwargs)

    @classmethod
    def from_spk_folder(cls, spk_folder, bin_size=1, preprocess=True, **kwargs):
        return cls(spk_folder=spk_folder, bin_size=bin_size, preprocess=preprocess, **kwargs)

    def __init__(self, spikes_arr=None, npz_file=None, mat_file=None, spk_files=None, spk_folder=None, bin_size=1,
                 preprocess=True):
        object.__init__(self)
        Restoreable.__init__(self)

        self.filename = npz_file or ''

        self._T = 0
        self._N = 0
        self._M = 0

        # TODO: instead of different parameters for different file formats use just two parameters, file and file_format
        if spikes_arr is not None:
            self._spikes_arr = spikes_arr
        elif npz_file is not None:
            if os.path.isfile(npz_file):
                hdlog.info("Loading Spikes from '%s'" % npz_file)
                self.filename = npz_file
                tmp = np.load(npz_file)
                self._spikes_arr = tmp[tmp.keys()[0]]
            else:
                hdlog.info("Not a file: '%s'" % npz_file)
                return
        elif mat_file is not None:
            import scipy.io
            mat = scipy.io.loadmat(mat_file)
            self._spikes_arr = mat[mat.keys()[0]]
        elif spk_files is not None:
            from bitstring import Bits

            self.neuron_to_file = []
            time_stamps = []
            self.bin_size = bin_size or 1

            for fname in spk_files:
                self.neuron_to_file.append(fname)
                f = open(fname, 'rb')
                p = Bits(f)
                fmt = str(p.length / 64) + ' * (intle:64)'
                time_stamps.append(p.unpack(fmt))
            self.load_from_spikes_times(time_stamps, bin_size=self.bin_size)
        elif spk_folder is not None:
            from bitstring import Bits

            self.neuron_to_file = []
            time_stamps = []
            self.bin_size = bin_size or 1
            fns = os.listdir(spk_folder)

            for i, fn in enumerate(fns):
                ext = os.path.splitext(fn)[1]
                if ext in ('.spk', ):  #Blanche spike format
                    self.neuron_to_file.append(fn)
                    f = open(os.path.join(spk_folder, fn), 'rb')
                    p = Bits(f)
                    fmt = str(p.length / 64) + ' * (intle:64)'
                    time_stamps.append(p.unpack(fmt))
                self.load_from_spikes_times(time_stamps, bin_size=self.bin_size)
        else:
            return

        spikes_shape = self._spikes_arr.shape
        if len(spikes_shape) == 2:  # single trial
            self._spikes_arr = self._spikes_arr.reshape((1, spikes_shape[0], spikes_shape[1]))

        self._T = self._spikes_arr.shape[0]
        self._N = self._spikes_arr.shape[1]
        self._M = self._spikes_arr.shape[2]

        if preprocess:
            self.preprocess()

    @property
    def spikes_arr(self):
        return self._spikes_arr

    @property
    def N(self):
        return self._N

    @property
    def M(self):
        return self._M

    @property
    def T(self):
        return self._T

    def restrict_to_most_active_neurons(self, top_neurons=None):
        """ (does not make a copy) if top_neurons is None: sorts the spike_arr """
        self._N = top_neurons or self._N
        activity = self._spikes_arr[:, :, :].mean(axis=0).mean(axis=1)
        idx = activity.argsort()
        self.idx = idx[-self._N:]
        self.mean_activities = activity[self.idx]
        self._spikes_arr = self._spikes_arr[:, idx[-self._N:], :]
        return self

    def to_windowed(self, window_size=1, trials=None, reshape=False):
        """ returns new Spikes object of 3d numpy arr of windowed spike trains:
                X:   T (num trials) x (window_size * N) x  (M - window_size + 1)
                                        binary vector out of a spike time series
            reshape: returns T(M - window_size + 1) x (ws * N) numpy binary vector
        """
        trials = trials or range(self._T)
        X = np.zeros((len(trials), window_size * self._N, self._M - window_size + 1))
        for c, t in enumerate(trials):
            for i in xrange(0, self._M - window_size + 1):
                X[c, :, i] = self._spikes_arr[t, :, i:window_size + i].ravel()

        if reshape:
            Y = np.zeros((X.shape[0] * X.shape[2], X.shape[1]))
            tot = 0
            for t in xrange(len(trials)):
                for j in xrange(X.shape[2]):
                    Y[tot, :] = X[t, :, j]
                    tot += 1
            return Y
        return Spikes(spikes_arr=X)

    def load_from_spikes_times(self, spike_times_lists, bin_size=1):
        """ loads a spike train from a list of arrays of spike times
            bin_size: in millisec
                - the jth item in the list corresponds to the jth neuron
                  it is the 1d array of spike times (micro sec) for that neuron
        """
        if len(spike_times_lists) == 0: return
        self.max_millisec = - np.inf
        for spike_times in spike_times_lists:
            milisec = 1. * (spike_times[-1]) / (10 ** 3)
            self.max_millisec = max(self.max_millisec, milisec)
        self._spikes_arr = np.zeros((len(spike_times_lists), np.int(self.max_millisec) / bin_size + 1))
        for c, spike_times in enumerate(spike_times_lists):
            for spike_time in spike_times:
                a = int(spike_time / (1000. * bin_size))
                if a < self._spikes_arr.shape[1]:
                    self._spikes_arr[c, a] = 1

    def preprocess(self):
        """ converts to binary """
        self._spikes_arr = np.double((np.sign(self._spikes_arr) + 1) // 2)

    def rasterize(self, trials=None, start=0, stop=None, save_png_name=None):
        """ return *new* (copied) numpy array of size (TN x M)
            trials: e.g. [1, 5, 6], None is all
            save_png_name: if not None then only saves
        """
        stop = stop or self._M
        trials = trials or range(self._T)
        sub_spikes_arr = self._spikes_arr[trials, :, start:stop]

        if save_png_name is not None:
            save_matrix_whole_canvas(sub_spikes_arr.reshape((len(trials) * self._N, stop - start)),
                                     save_png_name + '.png', cmap='gray')
        else:
            return sub_spikes_arr.copy().reshape((len(trials) * self._N, stop - start))

    def covariance(self, trials=None, start=0, stop=None, save_png_name=None):
        """ return *new* numpy array of size (T x N x N) which is covariance matrix betwn neurons
            trials: e.g. [0, 1, 5, 6], None is all
            save_png_name: if not None then only saves
        """
        stop = stop or self._M
        trials = trials or range(self._T)
        sub_spikes_arr = self._spikes_arr[trials, :, start:stop]

        new_arr = np.zeros((len(trials), self._N, self._N))
        for t, trial in enumerate(trials):
            new_arr[t] = np.cov(sub_spikes_arr[trial])
        new_arr /= new_arr.max()

        if save_png_name is not None:
            new_arr = new_arr.reshape(len(trials) * self._N, self._N)
            save_matrix_whole_canvas(new_arr, save_png_name + '.png', cmap='gray')
        else:
            return new_arr

    # i/o

    def save(self, filename='spikes', extra=None):
        """ save as numpy array .npz file """
        # TODO: document
        return super(Spikes, self)._save(filename=filename,
                                         attributes=self._SAVE_ATTRIBUTES_V1, version=self._SAVE_VERSION,
                                         extra=extra)

    @classmethod
    def load(cls, filename='spikes', load_extra=False):
        # TODO: document
        return super(Spikes, cls)._load(filename=filename, load_extra=load_extra)

    def _load_v1(self, contents, load_extra=False):
        hdlog.debug('Loading Spikes, format version 1')
        return Restoreable._load_attributes(self, contents, self._SAVE_ATTRIBUTES_V1)

    # representation

    def __repr__(self):
        return '<Spikes: {n} neurons, {m} bins, {t} trials>'.format(n=self._N, u=self._M, t=self._T)


# end of source
