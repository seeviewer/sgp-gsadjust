#!/usr/bin/env python
#  -*- coding: utf-8 -*-
"""
pyqt_modules.py
===============

PyQt models for GSadjust. Handles assembling input matrices for network adjustment.
--------------------------------------------------------------------------------------------------------------------

NB: PyQt models follow the PyQt CamelCase naming convention. All other methods/functions in GSadjust use PEP-8
lowercase_underscore convention.

This software is preliminary, provisional, and is subject to revision. It is being provided to meet the need for
timely best science. The software has not received final approval by the U.S. Geological Survey (USGS). No warranty,
expressed or implied, is made by the USGS or the U.S. Government as to the functionality of the software and related
material nor shall the fact of release constitute any such warranty. The software is provided on the condition that
neither the USGS nor the U.S. Government shall be held liable for any damages resulting from the authorized or
unauthorized use of the software.
"""
from PyQt5.QtCore import QVariant
from PyQt5 import QtGui, QtCore, QtWidgets
from matplotlib.dates import num2date, date2num
import numpy as np
import logging
import pickle
import data_objects
import datetime as dt
import copy
import os

# Constants for column headers
DATUM_STATION, DATUM_G, DATUM_SD, DATUM_DATE, MEAS_HEIGHT, GRADIENT, DATUM_RESIDUAL = range(7)
DELTA_STATION1, DELTA_STATION2, DELTA_TIME, DELTA_G, DELTA_DRIFTCORR, DELTA_SD, DELTA_ADJ_SD, DELTA_RESIDUAL = range(8)
ADJSTA_STATION, ADJSTA_G, ADJSTA_SD = range(3)


class ObsTreeItem(QtGui.QStandardItem):
    """
    Basic tree-view item used to populate data tree, used for Surveys, Loops, and Stations.
    Not used directly but inherited by ObsTreeStation, ...Loop, and ...Survey
    """
    def __init__(self):
        super(ObsTreeItem, self).__init__()
        self.setFlags(self.flags() |
                      QtCore.Qt.ItemIsEnabled |
                      QtCore.Qt.ItemIsEditable |
                      QtCore.Qt.ItemIsUserCheckable)

        self.setCheckState(QtCore.Qt.Checked)
        self.fontweight = QtGui.QFont.Normal
        self.cellcolor = QtCore.Qt.white


class ObsTreeStation(ObsTreeItem):
    """
    PyQt model for stations. Station data is stored as a Station object in .station
    """
    def __init__(self, k, station_name, station_count):
        """
        Create a new station from ChannelList object. The fields (lists) of the ChannelList are copies to the
        ObsTreeStation.
        :param k: ChannelList object.
        :param station_name: String
        :param station_count: Int
        """
        super(ObsTreeStation, self).__init__()  # call properties from the baseclass
        self.__dict__ = copy.deepcopy(k.__dict__)
        self.station_name = station_name
        self.station_count = station_count  # Records the number of times the station is occupied in a loop
        # For legacy .p files
        # if len(self.corr_g) == 0:
        #     self.corr_g = self.raw_grav

    def __str__(self):
        return self.station_name

    def _weights_(self):
        sdtmp = [self.sd[i] / np.sqrt(self.dur[i]) for i in range(len(self.t))]
        w = np.array([1. / (sdtmp[i] * sdtmp[i]) for i in range(len(self.t)) if self.keepdata[i] == 1])
        return w

    @classmethod
    def from_station(cls, station):
        """
        Create a station from an existing station. Used to clone stations.
        :param station: ObsTreeStation object to be copied
        :return: ObsTreeStation
        """
        temp = cls(station, station.station_name, station.station_count)
        temp.__dict__ = station.__dict__
        return temp

    @property
    def grav(self):
        """
        Applies tares to raw_grav
        :return: List
        """
        # if len(self.corr_g) == 0:
        #     self.corr_g = self.raw_grav
        data = np.array(self.raw_grav) + np.array(self.tare) + np.array(self.etc)
        return data.tolist()

    @property
    def name(self):
        return self.station_name

    @property
    def display_name(self):
        return self.station_name + ' (' + self.station_count + ')'

    @property
    def gmean(self):
        gtmp = np.array([self.grav[i] for i in range(len(self.t)) if self.keepdata[i] == 1])
        gmean = sum(gtmp * self._weights_()) / sum(self._weights_())
        return gmean

    @property
    def tmean(self):
        ttmp = np.array([date2num(self.t[i]) for i in range(len(self.t)) if self.keepdata[i] == 1])
        tmean = sum(ttmp * self._weights_()) / sum(self._weights_())
        return tmean

    @property
    def stdev(self):
        if self.sd[0] == -999:
            gtmp = np.array([self.grav[i] for i in range(len(self.t)) if self.keepdata[i] == 1])
            return float(np.std(gtmp))
        else:
            return np.sqrt(1. / sum(self._weights_()))


class ObsTreeLoop(ObsTreeItem):
    """
    PyQt model for Loops, parent item for stations. Loop attributes stored in .loop
    """
    def __init__(self, name):
        super(ObsTreeLoop, self).__init__()
        self.delta_model = DeltaTableModel()
        self.tare_model = TareTableModel()
        self.name = name
        self.drift_method = 'none'
        self.drift_cont_method = 0  # If continuous model, also need to keep track of which type of model
        self.drift_cont_startend = 0  # behavior at start/end. 0: extrapolate, 1: constant
        self.drift_netadj_method = 2  # If netadj method, keep track of polynomial degree
        self.meter = None  # Meter S/N, for the case where multiple meters are calibrated

    @property
    def meter_type(self):
        station = self.child(0)
        return station.meter_type

    @classmethod
    def from_simpleloop(cls, simple_loop):
        temp = cls(simple_loop.name)
        temp.__dict__ = simple_loop.__dict__
        temp.delta_model = DeltaTableModel()
        temp.tare_model = TareTableModel()
        for tare in simple_loop.tares:
            temp.tare_model.insertRows(tare, 0)
        return temp

    def populate(self, data):
        """
        Populate loop dictionary using data passed as an option. For now, only the 'single' option works.

        :param data: Passed to Loop.populate_station_dic()
        """
        self.meter = data.meter[0]
        prev_sta = data.station[0]
        ind_start = 0
        station_count_dic = dict()

        # loop over samples:
        for i in range(len(data.station)):
            curr_sta = data.station[i]
            if curr_sta != prev_sta:
                if prev_sta not in station_count_dic.keys():
                    station_count_dic[prev_sta] = 1
                else:
                    station_count_dic[prev_sta] += 1
                ind_end = i - 1
                # create a new ChannelList object:
                temp_sta = data.extract_subset_idx(ind_start, ind_end)
                obstreestation = ObsTreeStation(temp_sta, prev_sta, str(station_count_dic[prev_sta]))
                obstreestation.meter_type = data.meter_type
                logging.info('Station added: ' + prev_sta + str(station_count_dic[prev_sta]))
                ind_start = i
                self.appendRow([obstreestation, QtGui.QStandardItem('0'), QtGui.QStandardItem('0')])
            if i == len(data.station) - 1:
                # enter last data line
                ind_end = i
                if curr_sta not in station_count_dic.keys():
                    station_count_dic[curr_sta] = 1
                else:
                    station_count_dic[curr_sta] += 1

                # create a new Loop-type object:
                temp_sta = data.extract_subset_idx(ind_start, ind_end)
                obstreestation = ObsTreeStation(temp_sta, curr_sta, str(station_count_dic[curr_sta]))
                obstreestation.meter_type = data.meter_type
                logging.info('Station added: ' + curr_sta + str(station_count_dic[curr_sta]))
                self.appendRow([obstreestation, QtGui.QStandardItem('0'), QtGui.QStandardItem('0')])
            prev_sta = curr_sta

    def get_station_reoccupation(self, station):
        """
        Get index of station reoccupation. To be used iteratively within the populate_station_dic function
        :param station: Station for which a repeat occupation is sought.
        :return: index of station reoccupation
        """
        station_reoc = [sta[0] for sta, stakey in self.station_dic.items() if sta[0] == station]
        return len(station_reoc)

    def get_data_for_plot(self):
        """
        Retrieves data from loop that is used for plotting: occupations must be checked, and there must be
        more than one occupation at a station.
        :return: list of plot_data lists
        """
        unique_stations = set()
        plot_data = []
        for i in range(self.rowCount()):
            station = self.child(i)
            if self.child(i).data(role=QtCore.Qt.CheckStateRole) == 2:
                if (station.station_name, station.meter[0]) not in unique_stations:
                    unique_stations.add(station.station_name)

        for unique_station in unique_stations:
            x = []
            y = []
            for i in range(self.rowCount()):
                station = self.child(i)
                if self.child(i).data(role=QtCore.Qt.CheckStateRole) == 2:
                    if station.station_name == unique_station:
                        x.append(station.tmean)
                        y.append(station.gmean)
            plot_data.append([x, y, unique_station])

        # sort plot_data by initial x in each line
        plot_data_sorted = []
        exes = [x[0][0] for x in plot_data]

        # get index of sorted list
        idx = sorted(range(len(exes)), key=lambda m: exes[m])
        for i in idx:
            plot_data_sorted.append(plot_data[i])
        return plot_data_sorted

    def checked_stations(self):
        """
        Retrieves checked data from loop; used for calculating delta-gs in the "None" and "Continuous" drift options.
        :return: list of checked stations
        """
        data = []
        for i in range(self.rowCount()):
            station = self.child(i)
            if self.child(i).data(role=QtCore.Qt.CheckStateRole) == 2:
                data.append(station)
        return data

    def all_stations(self):
        data = []
        for i in range(self.rowCount()):
            station = self.child(i)
            data.append(station)
        return data

    def deltas(self):
        """
        Called when 'Populate delta table... menu item is selected. Applies SD settings in options.
        :param selection: Specifies how many deltas to populate: 'all', 'selectedsurvey', or 'selectedloop'.
        """
        deltas = []
        table = self.delta_model
        for i in range(table.rowCount()):
            delta = table.data(table.index(i, 0), role=QtCore.Qt.UserRole)
            deltas.append(delta)
            if self.parent().adjustment.adjustmentoptions.use_sigma_min:
                delta.adj_sd = max(self.parent().adjustment.adjustmentoptions.sigma_min, delta.sd)
        return deltas


class ObsTreeSurvey(ObsTreeItem):
    """
    A survey object is a little different than Loop or Station objects in that it doesn't have a corresponding
    data object. All relevant info is in this object.
    """

    def __init__(self, name):
        super(ObsTreeSurvey, self).__init__()
        # Both surveys and loops have delta models. The survey delta_model holds the observations used in an
        # adjustment, and may have deltas from one or more loops.
        self.name = name
        self.delta_model = DeltaTableModel()
        self.datum_model = DatumTableModel()
        self.results_model = ResultsTableModel()
        self.adjustment = data_objects.Adjustment()

    def __str__(self):
        return self.name

    @classmethod
    def from_simplesurvey(cls, simple_survey):
        """
        When loading a workspace, repopulate PyQt models
        """
        temp = cls(simple_survey.name)
        for delta in simple_survey.deltas:
            temp.delta_model.insertRows(delta, 0)
        for datum in simple_survey.datums:
            temp.datum_model.insertRows(datum, 0)
        temp.adjoptions = simple_survey.adjoptions
        return temp

    @property
    def unique_meters(self):
        """
        :return: List of unique gravity-meter IDs (serial numbers) used in the survey
        """
        meters = []
        for station in self.iter_stations():
            meters.append(station.meter[0])  # Get the first entry; Assume meter number can't change at a station
        return list(set(meters))

    @property
    def loop_count(self):
        a = self.loop_names
        return len(a)

    @property
    def loop_names(self):
        loops = []
        for i in range(self.rowCount()):
            loop = self.child(i)
            loops.append(int(loop.name))
        return loops

    def populate(self, survey_data, name='0'):
        logging.info('Survey added')
        obstreeloop = ObsTreeLoop(name)
        obstreeloop.populate(survey_data)
        self.appendRow([obstreeloop, QtGui.QStandardItem('0'), QtGui.QStandardItem('0')])

    def iter_stations(self):
        """
        Iterator
        :return: All of the stations in a campaign
        """
        for i in range(self.rowCount()):
            obstreeloop = self.child(i)
            for ii in range(obstreeloop.rowCount()):
                obstreestation = obstreeloop.child(ii)
                yield obstreestation

    def gravnet_inversion(self):
        """
        Writes input files for Gravnet.exe, runs the executable, and reads in the results
        """
        # TODO: method could probably be made static
        from gui_objects import show_message
        from data_objects import AdjustedStation
        dir_changed = False
        # Check that executable exists in current directory (it should, if run as compiled .exe
        if not os.path.exists('.\\gravnet.exe'):
            # if not found, it might be in the dist directory (i.e., running GSadjust.py)
            if os.path.exists('..\\dist\\gravnet.exe'):
                os.chdir('..\\dist')
                dir_changed = True
            # not found at all: error
            else:
                show_message('Gravnet.exe not found, aborting', 'Inversion error')
                logging.error('Inversion error, Gravnet.exe not found')
                return

        # If using gravnet with netadj drift option (including drift term in the network adjustment), a single
        # drift model is used for all observations in the adjustment. Check that the method is set to netadj
        # for all loops, otherwise show an error message and return.
        netadj = []
        for delta in self.adjustment.deltas:
            netadj.append(delta.ls_drift)
        unique_netadj = set(netadj)
        if len(unique_netadj) > 1:
            show_message('It appears that more than one polynomial degree was specified for different loops for the '
                         'network, or that some loops are not using the' +
                         ' adjutment drift option. When using Gravnet, all loops must have the same degree drift ' +
                         'model. Aborting.',
                         'Inversion error')
            return
        if len(unique_netadj) == 1:
            if list(unique_netadj)[0] == (None, None):
                drift_term = ''
            else:
                drift_term = '-T' + str(delta.ls_drift[1])

        # Remove old gravnet files
        try:
            os.remove(self.name + '.gra')
            os.remove(self.name + '.err')
            os.remove(self.name + '.his')
            os.remove(self.name + '.met')
            os.remove(self.name + '.res')
            os.remove(self.name + '.sta')
        except OSError:
            pass

        # Warn if station names will be truncated
        truncate_warning = False
        for delta in self.adjustment.deltas:
            if len(delta.sta1) > 6 or len(delta.sta2) > 6:
                truncate_warning = True
        if truncate_warning:
            show_message('One or more station names is longer than 6 characters. Names will be truncated to 6 '
                         'characters in the Gravnet input file. Please verify that names will still be unique '
                         'after truncating.',
                         'Inversion warning')

        # Write delta-g observation file
        dg_file = self.name + '_dg.obs'
        with open(dg_file, 'w') as fid:
            fid.write('start, end, difference (mgal), mjd (from), mjd (to),' +
                      ' reading (from, CU), reading (to, CU), standard deviation (mgal)\n')
            # Gravnet station names are limited to 6 characters
            for delta in self.adjustment.deltas:
                fid.write('{} {} {:0.6f} {} {} {:0.6f} {} {:0.6f}\n'.format(delta.sta1[:6],
                                                                            delta.sta2[:6],
                                                                            delta.dg / 1000.,
                                                                            delta.sta1_t,
                                                                            delta.sta2_t,
                                                                            delta.dg / 1000, '0',
                                                                            delta.adj_sd / 1000.))
        # Write absolute-g (aka datum, aka fix) file
        fix_file = self.name + '_fix.txt'
        with open(fix_file, 'w') as fid:
            for datum in self.adjustment.datums:
                fid.write(
                    '{} {:0.6f} {:0.3f}\n'.format(datum.station[:6], float(datum.g) / 1000., float(datum.sd) / 1000.))

        # Check if calibration coefficient is calculated
        if self.adjustment.adjustmentoptions.cal_coeff:
            if len(self.unique_meters) > 1:
                show_message("It appears more than one meter was used on the survey. Gravnet calculates a " +
                             "calibration coefficient for a single meter only. Use Numpy inversion " +
                             "to calculate meter-specific calibration coefficients",
                             "Inversion warning")
            if len(self.adjustment.datums) == 1:
                show_message("Two or more datum observations are required to calculate a calibration coefficient." +
                             " Aborting.", "Inversion warning")
                return
            # Run gravnet with calibration coefficient
            os.system('gravnet -D' + dg_file + ' -N' + self.name + ' -M2 -C1 ' + drift_term + ' -F' + fix_file)
            with open(self.name + '.met', 'r') as fid:
                symbol = ''
                while symbol != 'Y_l':
                    line = fid.readline().split()
                    symbol = line[0]
                meter_calib_params = fid.readline().split()
        else:
            # Run gravnet without calibration coefficient
            os.system('gravnet -D' + dg_file + ' -N' + self.name + ' -M2 ' + drift_term + ' -F' + fix_file)

        if drift_term != '':
            meter_drift_params = []
            with open(self.name + '.met', 'r') as fid:
                symbol = ''
                while symbol != 'Coefficients':
                    line = fid.readline().split()
                    symbol = line[0]
                order = int(line[-1])
                for i in range(order):
                    meter_drift_params.append(fid.readline().split())

        self.results_model.setData(0, 0, QtCore.Qt.UserRole)  # clears results table
        g_dic = dict()

        # Read gravnet results
        with open(self.name + '.gra', 'r') as fid:
            _ = fid.readline()  # Header line
            all_sd = []
            while True:
                fh = fid.readline()
                if len(fh) == 0:
                    break
                parts = fh.split()
                sta = parts[1]
                g = float(parts[2]) * 1000
                sd = float(parts[3]) * 1000
                all_sd.append(sd)
                if len(parts) == 4:
                    g_dic[sta] = g
                    self.results_model.insertRows(AdjustedStation(sta, g, sd), 0)
            self.adjustment.adjustmentresults.avg_stdev = np.mean(all_sd)

        dg_residuals = []

        # match up residuals
        for i in range(self.delta_model.rowCount()):
            ind = self.delta_model.createIndex(i, 0)
            chk = self.delta_model.data(ind, QtCore.Qt.CheckStateRole)
            tempdelta = self.delta_model.data(ind, QtCore.Qt.UserRole)
            if chk == 2:
                try:
                    adj_g1 = g_dic[tempdelta.sta1[:6]]
                    adj_g2 = g_dic[tempdelta.sta2[:6]]
                    adj_dg = adj_g2 - adj_g1
                    tempdelta.residual = adj_dg - tempdelta.dg
                    dg_residuals.append(tempdelta.residual)
                except KeyError:
                    show_message("Key error", "Key error")
            else:
                tempdelta.residual = -999.
            self.delta_model.setData(ind, tempdelta, QtCore.Qt.UserRole)

        datum_residuals = []
        for i in range(self.datum_model.rowCount()):
            ind = self.datum_model.createIndex(i, 0)
            tempdatum = self.datum_model.data(ind, QtCore.Qt.UserRole)
            if tempdatum.station[0:6] in g_dic.keys():
                adj_g1 = g_dic[tempdatum.station[:6]]
                residual = adj_g1 - (tempdatum.g - tempdatum.meas_height * tempdatum.gradient)
                datum_residuals.append(residual)
            else:
                residual = -999
            tempdatum.residual = residual
            self.datum_model.setData(ind, tempdatum, QtCore.Qt.UserRole)

        self.adjustment.adjustmentresults.min_dg_residual = np.min(dg_residuals)
        self.adjustment.adjustmentresults.max_dg_residual = np.max(dg_residuals)
        self.adjustment.adjustmentresults.min_datum_residual = np.min(datum_residuals)
        self.adjustment.adjustmentresults.max_datum_residual = np.max(datum_residuals)

        # Add calibration coefficient and/or drift coefficients to output text
        self.adjustment.adjustmentresults.text = []
        with open(self.name + '.sta', 'r') as fid:
            while True:
                fh = fid.readline()
                if len(fh) == 0:
                    break
                self.adjustment.adjustmentresults.text.append(fh)
            if self.adjustment.adjustmentoptions.cal_coeff:
                self.adjustment.adjustmentresults.text.append("\n\nGravimeter calibration coefficient: " +
                                                              str(1 + float(meter_calib_params[0])) + ' ± ' +
                                                              meter_calib_params[1])
            if drift_term != '':
                self.adjustment.adjustmentresults.text.append("\n\nGravimeter drift coefficient(s):\n ")
                for coeffs in meter_drift_params:
                    self.adjustment.adjustmentresults.text.append(coeffs[0] + ' ± ' + coeffs[1] + '\n')

        if dir_changed:
            os.chdir('..\\main_code')

    def numpy_inversion(self, output_root_dir, write_out_files='n'):
        """
        Least-squares network adjustment using numpy

        Parameters
        write_out_files:    (y/n): write output files for drift adjustment
                            (similar to MCGravi output files)
        output_root_dir     directory for writing output files
        """
        from gui_objects import show_message
        from data_objects import AdjustedStation
        self.adjustment.adjustmentresults.text = []

        # sta_dic_LS is a dictionary, key: station name, value: column for A matrix
        sta_dic_ls = self.get_station_indices()

        # get number of relative observations:
        n_rel_obs = len(self.adjustment.deltas)

        # number of absolute obs.
        n_abs_obs = len(self.adjustment.datums)

        if self.adjustment.adjustmentoptions.cal_coeff:
            if len(self.adjustment.datums) == 1:
                show_message("Two or more datum observations are required to calculate a calibration coefficient." +
                             " Aborting.", "Inversion warning")
                return
            n_meters = len(self.unique_meters)
            self.adjustment.meter_dic = dict(zip(self.unique_meters, range(n_meters + 1)))
        else:
            n_meters = 0

        nloops = 0
        for i in range(self.rowCount()):
            loop = self.child(i)
            if loop.data(role=QtCore.Qt.CheckStateRole) == 2:
                nloops += 1

        # number of unknowns:
        # TODO: temperature drift function
        drift_time = 0  # self.adjustment.adjustmentoptions.drift_time
        if self.adjustment.adjustmentoptions.use_model_temp:
            drift_temp = self.adjustment.adjustmentoptions.model_temp_degree
        else:
            drift_temp = 0

        # Drift may be included in the network adjustment for any or all loops. This section of code
        # builds some dicts used later to assemble the A matrix.
        ndrift = 0

        # Temporary var to compile all delta.ls_drift tuples: (loop.name, degree of drift model)
        ls_drift_list = []

        # dict of tuples, used to identify column of drift observation in A matrix:
        # (loop.name, (column relative to end of A matrix, drift degree)
        netadj_loop_keys = dict()

        # dict of unique delta.ls_drift values, used to cross-reference loop name with poly. degree
        # (the loop object only knows if the drift method is netadj, or not. The delta object stores
        # the degree of the drift polynomial, but doesn't know if the drift correction is netadj (a
        # delta could have a non (0,0) ls_drift value, but use some other drift corretion method.
        loop_ls_dict = dict()
        for delta in self.adjustment.deltas:
            ls_drift_list.append(delta.ls_drift)
        ls_drift_dict = dict(set(ls_drift_list))
        for i in range(self.rowCount()):
            obstreeloop = self.child(i)
            if obstreeloop.data(role=QtCore.Qt.CheckStateRole) == 2:
                loop_ls_dict[obstreeloop.name] = obstreeloop.drift_method
                if obstreeloop.drift_method == 'netadj':
                    ls_degree = ls_drift_dict[obstreeloop.name]
                    netadj_loop_keys[obstreeloop.name] = (ndrift, ls_degree)
                    ndrift += ls_degree

        # Initialize least squares matrices
        # number of unknowns                                                                   #
        nb_x = len(sta_dic_ls) + ndrift + drift_temp * nloops + n_meters
        # model matrix:
        A = np.zeros((n_rel_obs + n_abs_obs, nb_x))
        # weight matrix:
        P = np.zeros((n_rel_obs + n_abs_obs, n_rel_obs + n_abs_obs))  # pas sur
        # observation matrix:
        Obs = np.zeros((n_rel_obs + n_abs_obs, 1))
        # datum-free constraint vector:
        S = np.zeros((nb_x, 1))

        row = 0
        deltakeys =[]

        # Populate least squares matrices
        for delta in self.adjustment.deltas:
            deltakeys.append(delta.__hash__())
            Obs[row] = delta.dg
            P[row, row] = 1. / (delta.adj_sd ** 2)
            A[row, sta_dic_ls[delta.sta1]] = -1
            A[row, sta_dic_ls[delta.sta2]] = 1

            # Populate 1 column per gravimeter for calibration coefficient
            if self.adjustment.adjustmentoptions.cal_coeff:
                meter = delta.meter
                try:
                    A[row, self.adjustment.meter_dic[meter] + len(sta_dic_ls)] = delta.dg
                except:
                    show_message('Key error. Do Datum station names match delta observations?', 'Inversion error')

            # Populate column(s) for drift, if included in network adjustment
            if delta.ls_drift is not (0, 0):
                loop_name = delta.ls_drift[0]

                # It's possible for ls_drift to have been set, but the loop method to be something other than netadj
                if loop_name:
                    if loop_ls_dict[loop_name] == 'netadj':
                        for i in range(delta.ls_drift[1]):  # degree of polynomial
                            A[row, len(sta_dic_ls) + n_meters + netadj_loop_keys[loop_name][0] + i] = \
                                (delta.sta2_t - delta.sta1_t) ** (i + 1)

            S[sta_dic_ls[delta.sta1]] = 1
            S[sta_dic_ls[delta.sta2]] = 1
            row += 1

        # add datum observation (absolute station(s) or station(s) with fixed values)
        i = 0
        for datum in self.adjustment.datums:
            A[n_rel_obs + i, sta_dic_ls[datum.station]] = 1
            P[n_rel_obs + i, n_rel_obs + i] = 1. / datum.sd ** 2
            Obs[n_rel_obs + i] = datum.g
            i += 1

        # Do the inversion
        self.adjustment.A = A
        self.adjustment.P = P
        self.adjustment.Obs = Obs
        self.adjustment.S = S
        self.adjustment.dof = n_rel_obs + n_abs_obs - nb_x
        self.adjustment.python_lsq_inversion()

        # Populate results table
        for i in range(len(sta_dic_ls)):
            for key, val in sta_dic_ls.items():
                if val == i:
                    t = AdjustedStation(key, float(self.adjustment.X[i]), float(np.sqrt(self.adjustment.var[i])))
                    self.results_model.insertRows(t, 0)

        # Reset residuals to all -999's
        for i in range(self.delta_model.rowCount()):
            ind = self.delta_model.createIndex(i, 0)
            tempdelta = self.delta_model.data(ind, QtCore.Qt.UserRole)
            tempdelta.residual = -999.
            self.delta_model.setData(ind, tempdelta, QtCore.Qt.UserRole)

        # Matchup adjustment residuals with observations
        for i in range(n_rel_obs):
            key = deltakeys[i]
            resd = self.adjustment.r[i]
            for ii in range(self.delta_model.rowCount()):
                ind = self.delta_model.createIndex(ii, 0)
                tempdelta = self.delta_model.data(ind, QtCore.Qt.UserRole)
                if key == tempdelta.key:
                    break
            tempdelta.residual = float(resd[0])
            self.delta_model.setData(ind, tempdelta, QtCore.Qt.UserRole)

        datum_residuals = []
        for i in range(self.datum_model.rowCount()):
            ind = self.datum_model.createIndex(i, 0)
            tempdatum = self.datum_model.data(ind, QtCore.Qt.UserRole)
            if tempdatum.station in sta_dic_ls.keys():
                adj_idx = sta_dic_ls[tempdatum.station]
                adj_g1 = self.adjustment.X[adj_idx][0]
                residual = adj_g1 - (tempdatum.g - tempdatum.meas_height * tempdatum.gradient)
                datum_residuals.append(residual)
            else:
                residual = -999
            tempdatum.residual = residual
            self.datum_model.setData(ind, tempdatum, QtCore.Qt.UserRole)

        # calculate and display statistics:
        self.adjustment.lsq_statistics()

        # write output files
        text_out = list()
        text_out.append("Number of stations:                 {:d}\n".format(len(sta_dic_ls)))
        text_out.append("Number of loops:                    {:d}\n".format(nloops))
        text_out.append("Polynomial degree for time:         {:d}\n".format(drift_time))
        text_out.append("Polynomial degree for temperature:  {:d}\n".format(drift_temp))
        text_out.append("\n")
        text_out.append("Number of unknowns:                 {:d}\n".format(nb_x))
        text_out.append("Number of relative observations:    {:d}\n".format(n_rel_obs))
        text_out.append("Number of absolute observations:    {:d}\n".format(n_abs_obs))
        text_out.append("Degrees of freedom (nobs-nunknowns): {:d}\n".format(self.adjustment.dof))
        text_out.append("\n")
        text_out.append(
            "SD a posteriori:                    {:f}\n".format(
                float(np.sqrt(self.adjustment.VtPV / self.adjustment.dof))))
        text_out.append("chi square value:                   {:6.2f}\n".format(float(self.adjustment.chi2)))
        text_out.append("critical chi square value:          {:6.2f}\n".format(float(self.adjustment.chi2c)))
        if float(self.adjustment.chi2) < float(self.adjustment.chi2c):
            text_out.append("Chi-test accepted\n")
        else:
            text_out.append("Chi-test rejected\n")
        if self.adjustment.adjustmentoptions.cal_coeff:
            for k, v in self.adjustment.meter_dic.items():
                text_out.append("Calibration coefficient for meter {}: {:.4f} +/- {:.5f}".
                                format(k,
                                       float(1 - self.adjustment.X[len(sta_dic_ls) + v]),
                                       float(np.sqrt(self.adjustment.var[len(sta_dic_ls) + v]))))
        if netadj_loop_keys:
            text_out.append("Gravimeter drift coefficient(s):\n")
            for loop in netadj_loop_keys.items():  # this dict only has loops with netadj option
                text_out.append("Loop " + loop[0] + ": ")
                for i in range(loop[1][1]):  # degree of polynomial
                    text_out.append(str(self.adjustment.X[len(sta_dic_ls) +
                                                          n_meters +
                                                          loop[1][0] +
                                                          i][0]))

        self.adjustment.adjustmentresults.text = text_out

        # Write output to file
        if write_out_files == 'y':
            survdir = output_root_dir + os.sep + self.name
            if not os.path.exists(survdir):
                os.makedirs(survdir)
            tday = dt.datetime.now()

            with open(survdir + os.sep +
                      "LSresults_{:4d}{:02d}{:02d}_{:02d}{:02d}.dat".format(tday.year, tday.month, tday.day,
                                                                            tday.hour, tday.minute),
                      'w') as fid:
                for line in text_out:
                    fid.write(line)
            fid.close()

    def get_station_indices(self):
        """
        Creates a dictionary with unique (key=stationname, value=integer) pairs.
        :return: Dict with A-matrix index for each station
        """
        station_list = []
        sta_dic_ls = {}
        for delta in self.adjustment.deltas:
            station_list.append(delta.sta1)
            station_list.append(delta.sta2)
        station_list = list(set(station_list))
        for i in range(len(station_list)):
            sta_dic_ls[station_list[i]] = i
        return sta_dic_ls

    def populate_delta_model(self, loop=None):
        """
        Copy deltas fromt he delta_model shown on the drift tab to the mdoel shown on the adjustment tab.
        :param loop:
        :return:
        """
        self.delta_model.clearDeltas()
        # If just a single loop
        if type(loop) is ObsTreeLoop:
            for ii in range(loop.delta_model.rowCount()):
                if loop.delta_model.data(loop.delta_model.index(ii, 0), role=QtCore.Qt.CheckStateRole) == 2:
                    delta = loop.delta_model.data(loop.delta_model.index(ii, 0), role=QtCore.Qt.UserRole)
                    self.delta_model.insertRows(delta, 0)
        # Populate all loops
        elif loop is None:
            for i in range(self.rowCount()):
                loop = self.child(i)
                if loop.checkState() == QtCore.Qt.Checked:
                    for ii in range(loop.delta_model.rowCount()):
                        if loop.delta_model.data(loop.delta_model.index(ii, 0), role=QtCore.Qt.CheckStateRole) == 2:
                            delta = loop.delta_model.data(loop.delta_model.index(ii,0),role=QtCore.Qt.UserRole)
                            self.delta_model.insertRows(delta, 0)
        return True

class ObsTreeModel(QtGui.QStandardItemModel):
    """
    Tree model that shows station name, date, and average g value.

    The model is populated by appending stations to loops, and loops to surveys. The parent-child relationship is not
    explicitly stored.
    """

    # TODO: Implement drag and drop.
    def __init__(self):
        super(ObsTreeModel, self).__init__()
        self.stitem = None
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(['Name', 'Date', 'g (\u00b5Gal)'])

    refreshView = QtCore.pyqtSignal()

    def columnCount(self, QModelIndex_parent=None, *args, **kwargs):
        return 3

    def flags(self, QModelIndex):
        if not QModelIndex.isValid():
            return QtCore.Qt.ItemIsEnabled
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | \
               QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsDropEnabled | \
               QtCore.Qt.ItemIsUserCheckable

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole:
            if index.column() > 0:
                m = index.model().itemFromIndex(index.sibling(index.row(), 0))
            else:
                m = index.model().itemFromIndex(index)
            if type(m) is ObsTreeStation:
                if index.column() == 0:
                    return m.display_name
                if index.column() == 1:
                    return num2date(m.tmean).strftime('%Y-%m-%d %H:%M:%S')
                if index.column() == 2:
                    return '%1.1f' % m.gmean
            elif type(m) is ObsTreeLoop:
                if index.column() == 0:
                    return m.name
                if index.column() == 1:
                    return None
                if index.column() == 2:
                    return None
            elif type(m) is ObsTreeSurvey:
                if index.column() == 0:
                    return m.name
                if index.column() == 1:
                    return None
                if index.column() == 2:
                    return None
        elif role == QtCore.Qt.CheckStateRole:
            if index.column() == 0:
                m = index.model().itemFromIndex(index)
                return m.checkState()

    def setData(self, index, value, role):
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            m = index.model().itemFromIndex(index)
            if value == QtCore.Qt.Checked:
                m.setCheckState(QtCore.Qt.Checked)
            else:
                m.setCheckState(QtCore.Qt.Unchecked)
            self.dataChanged.emit(index, index)
            self.layoutChanged.emit()
            self.refreshView.emit()
            return True

        if role == QtCore.Qt.EditRole:
            if index.isValid() and 0 == index.column():
                import gui_objects
                m = index.model().itemFromIndex(index)
                if type(m) is ObsTreeStation:
                    old_name = m.station_name
                    new_name = str(value)
                    if new_name is not m.station_name:
                        rename_type = gui_objects.rename_dialog(old_name, new_name)
                        if rename_type is 'Loop':
                            loop = m.parent()
                            for i in range(loop.rowCount()):
                                item = loop.child(i, 0)
                                if item.station_name == old_name:
                                    item.station_name = new_name
                                    for iiii in range(len(item.station)):
                                        item.station[iiii] = new_name
                        if rename_type is 'Survey':
                            loop = m.parent()
                            survey = loop.parent()
                            for i in range(survey.rowCount()):
                                loop = survey.child(i, 0)
                                for ii in range(loop.rowCount()):
                                    item = loop.child(ii, 0)
                                    if item.station_name == old_name:
                                        item.station_name = new_name
                                        for iiii in range(len(item.station)):
                                            item.station[iiii] = new_name
                        if rename_type is 'Campaign':
                            campaign = index.model().invisibleRootItem()
                            for i in range(campaign.rowCount()):
                                survey = campaign.child(i, 0)
                                for ii in range(survey.rowCount()):
                                    loop = survey.child(ii, 0)
                                    for iii in range(loop.rowCount()):
                                        item = loop.child(iii, 0)
                                        if item.station_name == old_name:
                                            item.station_name = new_name
                                            for iiii in range(len(item.station)):
                                                item.station[iiii] = new_name
                        if rename_type is 'Station':
                            m.station_name = new_name
                            for iiii in range(len(m.station)):
                                m.station[iiii] = new_name
                        logging.info('Stations renamed from {} to {} in {}'.format(old_name, new_name,
                                                                                    rename_type))
                elif type(m) is ObsTreeLoop:
                    new_name = str(value)
                    old_name = m.name
                    logging.info('Loop renamed from {} to {}'.format(old_name, new_name))
                    m.name = new_name
            return True

    def checkState(self, index):
        if index.column > 0:
            m = index.model().itemFromIndex(index.sibling(index.row(), 0))
        else:
            m = index.model().itemFromIndex(index)
        return m.checkState()


    def insertRows(self, station, position, rows=1, index=QtCore.QModelIndex()):
        self.beginInsertRows(index, position, position + rows - 1)
        self.appendRow(station)
        self.endInsertRows()

    def obstree_export_data(self):
        """
        Removes PyQt objects from main data store, because they can't be pickled.

        PyQt tables to remove:
          From ObsTreeSurvey:
            delta_model = DeltaTableModel()
            datum_model = DatumTableModel()
            results_model = ResultsTableModel()
          From ObsTreeLoop:
            delta_model = DeltaTableModel()
            tare_model = TareTableModel()
          From ObsTreeStation:
            None (station table is generated on the fly)

        :return:
        List of lists
        """
        # For each survey
        surveys = []
        for i in range(self.rowCount()):
            obstreesurvey = self.itemFromIndex(self.index(i, 0))
            simple_survey = data_objects.SimpleSurvey(obstreesurvey)
            surveys.append(simple_survey)
        return surveys

    def load_workspace(self, data_path):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(None, 'Open File', data_path)
        with open(fname, "rb") as f:
            data = pickle.load(f)
        for survey in data:
            obstreesurvey = ObsTreeSurvey.from_simplesurvey(survey)
            for loop in survey.loops:
                obstreeloop = ObsTreeLoop.from_simpleloop(loop)
                # Call plot_drift to populate loop delta_models
                for station in loop.stations:
                    if hasattr(station, 'station_name'):  # Sometimes blank stations are generated, not sure why?
                        obstreestation = ObsTreeStation(station, station.station_name, station.station_count)
                        obstreeloop.appendRow([obstreestation,
                                               QtGui.QStandardItem('0'),
                                               QtGui.QStandardItem('0')])
                obstreesurvey.appendRow([obstreeloop,
                                         QtGui.QStandardItem('0'),
                                         QtGui.QStandardItem('0')])
            self.appendRow([obstreesurvey,
                                         QtGui.QStandardItem('0'),
                                         QtGui.QStandardItem('0')])

    def save_workspace(self, data_path):
        """
        Called when saving a workspace. Removes PyQt objects and calls pickle.dump
        :param data_path: full path to save file
        """
        # removes pyqt objects, which can't be pickled
        workspace_data = self.obstree_export_data()

        fname, _ = QtWidgets.QFileDialog.getSaveFileName(None, 'Save workspace as', data_path)
        if fname[-2:] != '.p':
            fname += '.p'
        with open(fname, "wb") as f:
            pickle.dump(workspace_data, f)
        logging.info('Pickling workspace to {}'.format(fname))


class RomanTableModel(QtCore.QAbstractTableModel):
    """
    Model to store the individual delta-g's calculated using the Roman-method. Shown on the drift tab.

    Shown on the drift tab.
    """

    def __init__(self):
        super(RomanTableModel, self).__init__()
        self.dgs = []

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.TextAlignmentRole:
            if orientation == QtCore.Qt.Horizontal:
                return QVariant(int(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter))
            return QVariant(int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter))
        if role != QtCore.Qt.DisplayRole:
            return QVariant()
        if orientation == QtCore.Qt.Horizontal:
            if section == 0:
                return QVariant("From")
            elif section == 1:
                return QVariant("To")
            elif section == 2:
                return QVariant("Delta g")
        return QVariant(int(section + 1))

    def insertRows(self, delta, position, rows=1, index=QtCore.QModelIndex()):
        self.beginInsertRows(QtCore.QModelIndex(), position, position + rows - 1)
        self.dgs.append(delta)
        self.endInsertRows()

    def rowCount(self, parent=None):
        return len(self.dgs)

    def columnCount(self, parent=None):
        return 3

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if index.isValid():
            delta = self.dgs[index.row()]
            column = index.column()
            if role == QtCore.Qt.DisplayRole:
                if column == 0:
                    return QVariant(delta.sta1)
                if column == 1:
                    return QVariant(delta.sta2)
                if column == 2:
                    return QVariant("%0.1f" % delta.dg)
            elif role == QtCore.Qt.UserRole:
                # check status definition
                return delta

    def setData(self, index, value, role):
        # type: (object, object, object) -> object
        """
        If a row is unchecked, update the keepdata value to 0 setData launched when role is acting value is
        QtCore.Qt.Checked or QtCore.Qt.Unchecked
        """
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            datum = self.datums[index.row()]
            if value == QtCore.Qt.Checked:
                datum.checked = 2
            elif value == QtCore.Qt.Unchecked:
                datum.checked = 0
            return True

        if role == QtCore.Qt.EditRole:
            if index.isValid() and 0 <= index.row():
                if len(str(value)) > 0:
                    datum = self.datums[index.row()]
                    column = index.column()
                    if column == DATUM_STATION:
                        datum.station = value
                    elif column == DATUM_G:
                        datum.g = float(value)
                    elif column == DATUM_SD:
                        datum.sd = float(value)
                    elif column == DATUM_DATE:
                        datum.date = value
                    self.dataChanged.emit(index, index)
            return True

    def flags(self, index):
        return (QtCore.Qt.ItemIsEnabled |
                QtCore.Qt.ItemIsSelectable |
                QtCore.Qt.ItemIsEditable)


# noinspection PyUnresolvedReferences
class DatumTableModel(QtCore.QAbstractTableModel):
    """
    Model to store Datums, shown on the adjust tab.
    """

    def __init__(self):
        super(DatumTableModel, self).__init__()
        self.datums = []

    signal_adjust_update_required = QtCore.pyqtSignal()

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.TextAlignmentRole:
            if orientation == QtCore.Qt.Horizontal:
                return QVariant(int(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter))
            return QVariant(int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter))
        if role != QtCore.Qt.DisplayRole:
            return QVariant()
        if orientation == QtCore.Qt.Horizontal:
            if section == DATUM_STATION:
                return QVariant("Station")
            elif section == DATUM_G:
                return QVariant("g")
            elif section == DATUM_SD:
                return QVariant("Std. dev.")
            elif section == DATUM_DATE:
                return QVariant("Date")
            elif section == MEAS_HEIGHT:
                return QVariant("Meas. height")
            elif section == GRADIENT:
                return QVariant("Gradient")
            elif section == DATUM_RESIDUAL:
                return QVariant("Residual")
        return QVariant(int(section + 1))

    def insertRows(self, datum, position, rows=1, index=QtCore.QModelIndex()):
        self.beginInsertRows(QtCore.QModelIndex(), position, position + rows - 1)
        self.datums.append(datum)
        self.endInsertRows()

    def rowCount(self, parent=None):
        return len(self.datums)

    def columnCount(self, parent=None):
        return 7

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if index.isValid():
            datum = self.datums[index.row()]
            column = index.column()
            if role == QtCore.Qt.DisplayRole:
                if column == DATUM_SD:
                    return '%0.2f' % datum.sd
                if column == DATUM_G:
                    return '%8.1f' % datum.g
                if column == DATUM_STATION:
                    return datum.station
                if column == DATUM_DATE:
                    return datum.date
                if column == MEAS_HEIGHT:
                    return '%0.2f' % datum.meas_height
                if column == GRADIENT:
                    return '%0.2f' % datum.gradient
                if column == DATUM_RESIDUAL:
                    return '%0.1f' % datum.residual

            elif role == QtCore.Qt.CheckStateRole:
                # check status definition
                if index.column() == 0:
                    return self.checkState(datum)

            elif role == QtCore.Qt.UserRole:
                # check status definition
                return datum

    def checkState(self, datum):
        """
        By default, everything is checked. If keepdata property from the ChannelList object is 0, it is unchecked
        """
        if datum.checked == 0:
            # self.unchecked[index]= QtCore.Qt.Unchecked
            # return self.unchecked[index]
            return QtCore.Qt.Unchecked
        else:
            return QtCore.Qt.Checked

    def setData(self, index, value, role):
        # type: (object, object, object) -> object
        """
        If a row is unchecked, update the keepdata value to 0 setData launched when role is acting value is
        QtCore.Qt.Checked or QtCore.Qt.Unchecked
        """
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            datum = self.datums[index.row()]
            if value == QtCore.Qt.Checked:
                datum.checked = 2
            elif value == QtCore.Qt.Unchecked:
                datum.checked = 0
            self.dataChanged.emit(index, index)
            self.signal_adjust_update_required.emit()
            return True

        if role == QtCore.Qt.EditRole:
            if index.isValid() and 0 <= index.row():
                if len(str(value)) > 0:
                    datum = self.datums[index.row()]
                    column = index.column()
                    if column == DATUM_STATION:
                        datum.station = str(value)
                    elif column == DATUM_G:
                        datum.g = float(value)
                    elif column == DATUM_SD:
                        datum.sd = float(value)
                    elif column == DATUM_DATE:
                        datum.date = value
                    elif column == MEAS_HEIGHT:
                        datum.meas_height = float(value)
                    elif column == GRADIENT:
                        datum.gradient = float(value)
                    self.dataChanged.emit(index, index)
            return True

        if role == QtCore.Qt.UserRole:
            self.datums[index.row()] = value
            self.dataChanged.emit(index, index)

    def flags(self, index):
        return (QtCore.Qt.ItemIsUserCheckable |
                QtCore.Qt.ItemIsEnabled |
                QtCore.Qt.ItemIsSelectable |
                QtCore.Qt.ItemIsEditable)

    def clearDatums(self):
        self.beginRemoveRows(self.index(0, 0), 0, self.rowCount())
        self.datums = []
        self.endRemoveRows()
        # The ResetModel calls is necessary to remove blank rows from the table view.
        self.beginResetModel()
        self.endResetModel()
        return QVariant()


class TareTableModel(QtCore.QAbstractTableModel):
    """
    Model to store tares (offsets)
    """

    def __init__(self):
        super(TareTableModel, self).__init__()
        self.tares = []

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.TextAlignmentRole:
            if orientation == QtCore.Qt.Horizontal:
                return QVariant(int(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter))
            return QVariant(int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter))
        if role != QtCore.Qt.DisplayRole:
            return QVariant()
        if orientation == QtCore.Qt.Horizontal:
            if section == 0:
                return QVariant("Date")
            elif section == 1:
                return QVariant("Time")
            elif section == 2:
                return QVariant("Tare (\u00b5Gal)")
        return QVariant(int(section + 1))

    def insertRows(self, tare, position=0, rows=1, index=QtCore.QModelIndex()):
        self.beginInsertRows(QtCore.QModelIndex(), position, position + rows - 1)
        self.tares.append(tare)
        self.endInsertRows()

    def rowCount(self, parent=None):
        return len(self.tares)

    def columnCount(self, parent=None):
        return 3

    def data(self, index, role):
        if index.isValid():
            tare = self.tares[index.row()]
            column = index.column()
            # print 'c'+str(column)
            if role == QtCore.Qt.DisplayRole:
                if column == 0:
                    return tare.date
                elif column == 1:
                    return tare.time
                elif column == 2:
                    return QVariant("%0.1f" % tare.tare)

            elif role == QtCore.Qt.CheckStateRole:
                if index.column() == 0:
                    return self.checkState(tare)

            elif role == QtCore.Qt.UserRole:
                return tare

    def setData(self, index, value, role):
        """
        If a row is unchecked, update the keepdata value to 0 setData launched when role is acting value is
        QtCore.Qt.Checked or QtCore.Qt.Unchecked
        """
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            tare = self.tares[index.row()]
            if value == QtCore.Qt.Checked:
                tare.checked = 2
            elif value == QtCore.Qt.Unchecked:
                tare.checked = 0
            return True
        if role == QtCore.Qt.EditRole:
            if index.isValid() and 0 <= index.row():
                tare = self.tares[index.row()]
                column = index.column()
                if len(str(value)) > 0:
                    if column == 0:
                        tare.date = float(value)
                    elif column == 1:
                        tare.time = float(value)
                    elif column == 2:
                        tare.tare = float(value)
                    self.dataChanged.emit(index, index)
                return True
        if role == QtCore.Qt.UserRole:
            self.tares[index.row()] = value

    def clearTares(self):
        self.beginRemoveRows(self.index(0, 0), 0, self.rowCount())
        self.tares = []
        self.endRemoveRows()
        # The ResetModel calls is necessary to remove blank rows from the table view.
        self.beginResetModel()
        self.endResetModel()
        return QVariant()

    def flags(self, index):
        return QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled | \
               QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable

    def checkState(self, tare):
        """
        By default, everything is checked. If keepdata property from the ChannelList object is 0, it is unchecked
        """
        if tare.checked == 0:
            return QtCore.Qt.Unchecked
        else:
            return QtCore.Qt.Checked


class ResultsTableModel(QtCore.QAbstractTableModel):
    """
    Model to store network-adjusted gravity values.

    There is one ResultsTableModel per survey.
    """

    def __init__(self):
        super(ResultsTableModel, self).__init__()
        self.adjusted_stations = []

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.TextAlignmentRole:
            if orientation == QtCore.Qt.Horizontal:
                return QVariant(int(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter))
            return QVariant(int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter))
        if role != QtCore.Qt.DisplayRole:
            return QVariant()
        if orientation == QtCore.Qt.Horizontal:
            if section == ADJSTA_STATION:
                return QVariant("Station")
            elif section == ADJSTA_G:
                return QVariant("g")
            elif section == ADJSTA_SD:
                return QVariant("Std. dev")
        return QVariant(int(section + 1))

    def insertRows(self, adjusted_station, position, rows=1, index=QtCore.QModelIndex()):
        self.beginInsertRows(QtCore.QModelIndex(), position, position + rows - 1)
        self.adjusted_stations.append(adjusted_station)
        self.endInsertRows()

    def rowCount(self, parent=None):
        return len(self.adjusted_stations)

    def columnCount(self, parent=None):
        return 3

    def data(self, index, role):
        if index.isValid():
            sta = self.adjusted_stations[index.row()]
            column = index.column()
            if role == QtCore.Qt.DisplayRole:
                if column == ADJSTA_STATION:
                    return sta.station
                elif column == ADJSTA_G:
                    return '%8.1f' % sta.g
                elif column == ADJSTA_SD:
                    return '%1.1f' % sta.sd
            if role == QtCore.Qt.UserRole:
                return sta

    def setData(self, index, value, role):
        # type: (object, object, object) -> object
        """
        If a row is unchecked, update the keepdata value to 0 setData launched when role is acting value is
        QtCore.Qt.Checked or QtCore.Qt.Unchecked
        """
        if role == QtCore.Qt.UserRole:
            self.adjusted_stations = []
            return QVariant()
        # return QtCore.QAbstractTableModel.setData(self, index, value, role)

    def flags(self, index):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def copyToClipboard(self):
        """
        Copies results tble to clipboard. Table needs to be selected first by clicking in the upper left corner.
        """
        clipboard = ""

        for r in range(self.rowCount()):
            for c in range(self.columnCount()):
                idx = self.index(r, c)
                clipboard += str(self.data(idx, role=QtCore.Qt.DisplayRole))
                if c != (self.columnCount() - 1):
                    clipboard += '\t'
            clipboard += '\n'

        # copy to the system clipboard
        sys_clip = QtWidgets.QApplication.clipboard()
        sys_clip.setText(clipboard)

    def clearResults(self):

        self.beginRemoveRows(self.index(0, 0), 0, self.rowCount())
        self.adjusted_stations = []
        self.endRemoveRows()
        # The ResetModel calls is necessary to remove blank rows from the table view.
        self.beginResetModel()
        self.endResetModel()
        return QVariant()


class DeltaTableModel(QtCore.QAbstractTableModel):
    """
    Model that stores delta-g's used in network adjustment. Used on the network adjustment tab and as the Roman
    average table (bottom right table when using Roman method drift correction).

    There is one DeltaTableModel per survey. The delta-g's that populate the model depend on the drift method used;
    if the Roman method is used, the delta-g's are the average of the individual delta-g's in the RomanTableModel.
    """

    def __init__(self):
        super(DeltaTableModel, self).__init__()
        self.deltas = []
        self.disabled_list = []

    signal_adjust_update_required = QtCore.pyqtSignal()

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.TextAlignmentRole:
            if orientation == QtCore.Qt.Horizontal:
                return QVariant(int(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter))
            return QVariant(int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter))
        if role != QtCore.Qt.DisplayRole:
            return QVariant()
        if orientation == QtCore.Qt.Horizontal:
            if section == DELTA_STATION1:
                return QVariant("From")
            elif section == DELTA_STATION2:
                return QVariant("To")
            elif section == DELTA_TIME:
                return QVariant("Time")
            elif section == DELTA_G:
                return QVariant("Delta-g")
            elif section == DELTA_DRIFTCORR:
                return QVariant("Drift correction")
            elif section == DELTA_SD:
                return QVariant("Std dev")
            elif section == DELTA_ADJ_SD:
                return QVariant("SD for adj.")
            elif section == DELTA_RESIDUAL:
                return QVariant("Residual")
        return QVariant(int(section + 1))

    def insertRows(self, delta, position, rows=1, index=QtCore.QModelIndex()):
        self.beginInsertRows(QtCore.QModelIndex(), position, position + rows - 1)
        self.deltas.append(delta)
        self.endInsertRows()

    def rowCount(self, parent=None):
        return len(self.deltas)

    def columnCount(self, parent=None):
        return 8

    def data(self, index, role):
        if index.isValid():
            delta = self.deltas[index.row()]
            column = index.column()
            if role == QtCore.Qt.ForegroundRole:
                if delta.type is 'normal':
                    if delta.station1.data(role=QtCore.Qt.CheckStateRole) == 2 and \
                            delta.station2.data(role=QtCore.Qt.CheckStateRole) == 2:
                        brush = QtGui.QBrush(QtCore.Qt.black)
                    else:
                        if delta.station1.data(role=QtCore.Qt.CheckStateRole) == 2:
                            if column == 0:
                                brush = QtGui.QBrush(QtCore.Qt.darkGray)
                            else:
                                brush = QtGui.QBrush(QtCore.Qt.lightGray)
                        elif delta.station2.data(role=QtCore.Qt.CheckStateRole) == 2:
                            if column == 1:
                                brush = QtGui.QBrush(QtCore.Qt.darkGray)
                            else:
                                brush = QtGui.QBrush(QtCore.Qt.lightGray)
                        else:
                            brush = QtGui.QBrush(QtCore.Qt.lightGray)
                elif delta.type is 'list' or delta.type is 'three_point':
                    brush = QtGui.QBrush(QtCore.Qt.black)
                else:
                    brush = QtGui.QBrush(QtCore.Qt.black)
                return brush
            if role == QtCore.Qt.DisplayRole:
                if column == DELTA_STATION1:
                    return delta.sta1
                elif column == DELTA_STATION2:
                    return delta.sta2
                elif column == DELTA_TIME:
                    return dt.datetime.utcfromtimestamp((delta.time() - 719163) * 86400.).strftime('%Y-%m-%d %H:%M:%S')
                elif column == DELTA_G:
                    return QVariant("%0.1f" % delta.dg)
                elif column == DELTA_DRIFTCORR:
                    return QVariant("%0.1f" % delta.driftcorr)
                elif column == DELTA_SD:
                    return QVariant("%0.1f" % delta.sd)
                elif column == DELTA_ADJ_SD:
                    return QVariant("%0.1f" % delta.adj_sd)
                elif column == DELTA_RESIDUAL:
                    return QVariant("%0.1f" % delta.residual)

            elif role == QtCore.Qt.CheckStateRole:
                if index.column() == 0:
                    return self.checkState(delta)

            elif role == QtCore.Qt.UserRole:
                return delta

    def setData(self, index, value, role):
        """
        If a row is unchecked, update the keepdata value to 0 setData launched when role is acting value is
        QtCore.Qt.Checked or QtCore.Qt.Unchecked
        """
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            delta = self.deltas[index.row()]
            if value == QtCore.Qt.Checked:
                delta.checked = 2
                if index.row() in self.disabled_list:
                    self.disabled_list.remove(index.row())
            elif value == QtCore.Qt.Unchecked:
                delta.checked = 0
                self.disabled_list.append(index.row())
            self.signal_adjust_update_required.emit()
            return True
        if role == QtCore.Qt.EditRole:
            if index.isValid() and 0 <= index.row():
                delta = self.deltas[index.row()]
                column = index.column()
                if len(str(value)) > 0:
                    if column == DELTA_ADJ_SD:
                        delta.adj_sd = float(value)
                    self.dataChanged.emit(index, index)
                return True
        if role == QtCore.Qt.UserRole:
            self.deltas[index.row()] = value

    def clearDeltas(self):
        self.beginRemoveRows(self.index(0, 0), 0, self.rowCount())
        self.deltas = []
        self.endRemoveRows()
        # The ResetModel calls is necessary to remove blank rows from the table view.
        self.beginResetModel()
        self.endResetModel()
        return QVariant()

    def updateTable(self):
        self.beginResetModel()
        self.endResetModel()
        return QVariant()

    def flags(self, index):
        return QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled | \
               QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable

    def checkState(self, delta):
        """
        By default, everything is checked. If keepdata property from the ChannelList object is 0, it is unchecked
        """
        if delta.checked == 0:
            return QtCore.Qt.Unchecked
        else:
            return QtCore.Qt.Checked


class ScintrexTableModel(QtCore.QAbstractTableModel):
    """
    Model to store Scintrex data.

    There is one ScintrexTableModel (or BurrisTableModel) per station occupation. The model is created dynamically
    each time a station is selected in the tree view on the data tab, rather than stored in memory.


    The station position in the data hierarchy are stored, so that if a modification is triggered, the original data
    can be accessed and changed accordingly (keysurv,keyloop,keysta)

    by default, all table entries are checked (this can be modified to allow pre-check based on user criteria (tiltx,
    tilty,...)). Then, if one is unchecked, the keepdata property of the ChannelList object at the table row position
    is set to 0

    properties:
    __headers:            table header
    unchecked:            a dictionnary of unchecked items. Keys are item
                          indexes, entries are states
    ChannelList_obj:      an object of ChannelList-type: used to store the
                          table data as the structured data
    arraydata:            an array representation of the data from the
                          ChannelList_obj
    keysurv:              the key of a survey object within the grav_obj
                          hierarchy
    keyloop:              the key of a loop object within the grav_obj
                          hierarchy
    keysta:               the key of a station object within the grav_obj
                          hierarchy
    """

    updateCoordinates = QtCore.pyqtSignal()
    signal_adjust_update_required = QtCore.pyqtSignal()

    def __init__(self, ChannelList_obj, parent=None):
        self.__headers = ["station", "date/time", "t (mn)", u"g (\u00b5gal)", u"sd (\u00b5gal)",
                          "tiltx", "tilty", "temp (K)", "dur (s)", "rej"]
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.unchecked = {}
        self.createArrayData(ChannelList_obj)

    def createArrayData(self, ChannelList_obj):
        """
        Create the np array data for table display, and update the ChannelList_obj. This function can be called from
        outside to update the table display
        """
        self.ChannelList_obj = ChannelList_obj
        self.arraydata = np.concatenate((ChannelList_obj.station,
                                         np.array(ChannelList_obj.t),
                                         (date2num(ChannelList_obj.t) - date2num(ChannelList_obj.t[0])) * 24 * 60,
                                         np.array(ChannelList_obj.grav),
                                         np.array(ChannelList_obj.sd), ChannelList_obj.tiltx,
                                         ChannelList_obj.tilty, ChannelList_obj.temp, ChannelList_obj.dur,
                                         ChannelList_obj.rej)).reshape(len(ChannelList_obj.t), 10, order='F')

    def rowCount(self, parent=None):
        return len(self.ChannelList_obj.t)

    def columnCount(self, parent):
        return len(self.__headers)

    def flags(self, index):
        return QtCore.Qt.ItemIsUserCheckable | \
               QtCore.Qt.ItemIsEnabled | \
               QtCore.Qt.ItemIsSelectable

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == QtCore.Qt.DisplayRole:
            # view definition
            row = index.row()
            column = index.column()
            if self.__headers[column] == "t (mn)":
                strdata = "%2.1f" % self.arraydata[row][column]
            elif self.__headers[column] == "rej":
                strdata = "%2.0f" % self.arraydata[row][column]
            elif self.__headers[column] == "dur (s)":
                strdata = "%3.0f" % self.arraydata[row][column]
            elif self.__headers[column] == u"g (\u00b5gal)" or \
                    self.__headers[column] == u"sd (\u00b5gal)":
                strdata = "%8.0f" % self.arraydata[row][column]
            else:
                strdata = str(self.arraydata[row][column])
            return strdata

        if role == QtCore.Qt.CheckStateRole:
            # check status definition
            if index.column() == 0:
                return self.checkState(index)

    def checkState(self, index):
        """
        By default, everything is checked. If keepdata property from the ChannelList object is 0, it is unchecked
        """
        if self.ChannelList_obj.keepdata[index.row()] == 0:
            self.unchecked[index] = QtCore.Qt.Unchecked
            return self.unchecked[index]
        else:
            return QtCore.Qt.Checked

    def setData(self, index, value, role):
        # type: (object, object, object) -> object
        """
        if a row is unchecked, update the keepdata value to 0 setData launched when role is acting value is
        QtCore.Qt.Checked or QtCore.Qt.Unchecked
        """
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            if value == QtCore.Qt.Checked:
                self.ChannelList_obj.keepdata[index.row()] = 1
            elif value == QtCore.Qt.Unchecked:
                self.unchecked[index] = value
                self.ChannelList_obj.keepdata[index.row()] = 0
            self.signal_adjust_update_required.emit()
            self.dataChanged.emit(index, index)
            return True

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                if section < len(self.__headers):
                    return self.__headers[section]
                else:
                    return "not implemented"


# noinspection PyUnresolvedReferences
class BurrisTableModel(QtCore.QAbstractTableModel):
    """
    Model to store Burris data.

    There is one BurrisTableModel (or ScintrexTableModel) per station occupation. The model is created dynamically
    each time a station is selected in the tree view on the data tab, rather than stored in memory.

    The station position in the data hierarchy are stored, so that if a modification is triggered, the original data
    can be accessed and changed accordingly (keysurv,keyloop,keysta)

    by default, all table entries are checked (this can be modified to allow pre-check based on user criteria (tiltx,
    tilty,...)). Then, if one is unchecked, the keepdata property of the ChannelList object at the table row position
    is set to 0

    properties:
    __headers:            table header
    unchecked:            a dictionary of unchecked items. Keys are item
                          indexes, entries are states
    ChannelList_obj:      an object of ChannelList-type: used to store the
                          table data as the structured data
    arraydata:            an array representation of the data from the
                          ChannelList_obj
    keysurv:              the key of a survey object within the grav_obj
                          hierarchy
    keyloop:              the key of a loop object within the grav_obj
                          hierarchy
    keysta:               the key of a station object within the grav_obj
                          hierarchy
    """

    def __init__(self, ChannelList_obj, parent=None):
        self.__headers = ["Station", "Oper", "Meter", "Date", u"g (\u00b5gal)", "Dial setting", "Feedback",
                          "Tide corr.", "Elev.", "Lat", "Long"]
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.unchecked = {}
        self.ChannelList_obj = None
        self.createArrayData(ChannelList_obj)
        self.arraydata = None

    updateCoordinates = QtCore.pyqtSignal()
    signal_adjust_update_required = QtCore.pyqtSignal()

    def createArrayData(self, ChannelList_obj):
        """
        Create the np array data for table display, and update the ChannelList_obj. This function can be called from
        outside to update the table display
        """
        # channel list attributes aren't specified in advance, so don't worry whether it's Burris or CG5 data
        self.ChannelList_obj = ChannelList_obj
        self.arraydata = np.concatenate((ChannelList_obj.station,
                                         ChannelList_obj.oper,
                                         ChannelList_obj.meter,
                                         date2num(ChannelList_obj.t),
                                         np.array(ChannelList_obj.grav),
                                         np.array(ChannelList_obj.dial),
                                         np.array(ChannelList_obj.feedback),
                                         np.array(ChannelList_obj.etc),
                                         np.array(ChannelList_obj.elev),
                                         np.array(ChannelList_obj.lat),
                                         np.array(ChannelList_obj.long))). \
            reshape(len(ChannelList_obj.t), 11, order='F')

    def rowCount(self, parent=None):
        return len(self.ChannelList_obj.t)

    def columnCount(self, parent=None):
        return len(self.__headers)

    def flags(self, index):
        return QtCore.Qt.ItemIsUserCheckable | \
               QtCore.Qt.ItemIsEnabled | \
               QtCore.Qt.ItemIsSelectable | \
               QtCore.Qt.ItemIsEditable

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == QtCore.Qt.DisplayRole:
            if self.arraydata is not None:
                row = index.row()
                column = index.column()
                strdata = str(self.arraydata[row][column])
                if self.__headers[column] == "Date":
                    strdata = num2date(float(self.arraydata[row][column])).strftime('%Y-%m-%d %H:%M:%S')
                if self.__headers[column] == u"g (µGal)":
                    strdata = "%0.1f" % self.arraydata[row][column]
                if self.__headers[column] == u"Tide corr.":
                    strdata = "%0.1f" % float(self.arraydata[row][column])
                return strdata

        if role == QtCore.Qt.CheckStateRole:
            # check status definition
            if index.column() == 0:
                return self.checkState(index)

    def checkState(self, index):
        """
        By default, everything is checked. If keepdata property from the ChannelList object is 0, it is unchecked
        """
        if self.ChannelList_obj.keepdata[index.row()] == 0:
            self.unchecked[index] = QtCore.Qt.Unchecked
            return self.unchecked[index]
        else:
            return QtCore.Qt.Checked

    def setData(self, index, value, role):
        """
        If a row is unchecked, update the keepdata value to 0 setData launched when role is acting value is
        QtCore.Qt.Checked or QtCore.Qt.Unchecked
        """
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:

            if value == QtCore.Qt.Checked:
                self.ChannelList_obj.keepdata[index.row()] = 1
            elif value == QtCore.Qt.Unchecked:
                self.unchecked[index] = value
                self.ChannelList_obj.keepdata[index.row()] = 0
            self.signal_adjust_update_required.emit()
            self.dataChanged.emit(index, index)
            return True

        elif role == QtCore.Qt.EditRole:
            if index.isValid() and 0 <= index.row():
                if len(str(value)) > 0:
                    attr = None
                    if index.column() == 1:  # Oper
                        self.arraydata[index.row()][index.column()] = value
                        attr = 'oper'
                    if index.column() == 2:  # Meter
                        self.arraydata[index.row()][index.column()] = value
                        attr = 'meter'
                    if index.column() == 9:  # Lat
                        self.arraydata[index.row()][index.column()] = float(value)
                        attr = 'lat'
                        self.updateCoordinates.emit()
                    if index.column() == 10:  # Long
                        self.arraydata[index.row()][index.column()] = float(value)
                        attr = 'long'
                        self.updateCoordinates.emit()
                    if attr is not None:
                        self.dataChanged.emit(index, index)
                        return True

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                if section < len(self.__headers):
                    return self.__headers[section]
                else:
                    return "not implemented"


class GravityChangeModel(QtCore.QAbstractTableModel):
    """
    Model to store gravity change between surveys.

    There is only one such model per campaign. Gravity change is calculated when the respective menu item is chosen.
    """

    def __init__(self, table, header, parent=None):
        self.__headers = header
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.unchecked = {}
        self.createArrayData(table)

    def createArrayData(self, table):
        """
        Create the np array data for table display, and update the ChannelList_obj. This function can be called from
        outside to update the table display
        """
        array = np.array(table).transpose()
        self.array_data = array

    def rowCount(self, parent=None):
        return self.array_data.shape[0]

    def columnCount(self, parent=None):
        return len(self.__headers)

    def flags(self, index):
        return QtCore.Qt.ItemIsEnabled | \
               QtCore.Qt.ItemIsSelectable

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == QtCore.Qt.DisplayRole:
            row = index.row()
            column = index.column()
            string_data = str(self.array_data[row][column])
            return string_data

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                if section < len(self.__headers):
                    return self.__headers[section]
                else:
                    return "not implemented"

