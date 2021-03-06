#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
menus.py
===============

Menus for GSadjust
--------------------------------------------------------------------------------------------------------------------

This software is preliminary, provisional, and is subject to revision. It is being provided to meet the need for
timely best science. The software has not received final approval by the U.S. Geological Survey (USGS). No warranty,
expressed or implied, is made by the USGS or the U.S. Government as to the functionality of the software and related
material nor shall the fact of release constitute any such warranty. The software is provided on the condition that
neither the USGS nor the U.S. Government shall be held liable for any damages resulting from the authorized or
unauthorized use of the software.
"""
from PyQt5 import QtWidgets
from gui_objects import about_dialog


class menus:
    def __init__(self, mainProg):
        self.mainProg = mainProg
        """
        Menu creation
        """
        #######################################################################
        # File Menu:
        #######################################################################
        self.mnFile = self.mainProg.menuBar().addMenu("&File")
        # for file opening
        self.mnFileOpenScintrexFile = self.create_action("&Load raw CG-3/CG-5 data...",
                                                         shortcut="Ctrl+o",
                                                         slot=lambda meter='Scintrex':
                                                         self.mainProg.open_raw_data('Scintrex'),
                                                         tip="Open data file",
                                                         enabled=True)
        self.mnFileOpenBurrisFile = self.create_action("Load raw &Burris data...",
                                                       shortcut="Ctrl+b",
                                                       slot=lambda meter='Burris':
                                                       self.mainProg.open_raw_data('Burris'),
                                                       tip="Open data file",
                                                       enabled=True)
        self.mnFileOpenCG6File = self.create_action("Load raw CG-6 data file...",
                                                    shortcut="Ctrl+6",
                                                    slot=lambda meter='CG6': self.mainProg.open_raw_data('CG6'),
                                                    tip="Open data file",
                                                    enabled=True)
        self.mnFileAppendSurvey = self.create_action("Append survey to campaign...",
                                                     slot=lambda meter='choose': self.mainProg.open_raw_data('choose'),
                                                     enabled=False)
        self.mnFileAppendLoop = self.create_action("Append loop to current survey...",
                                                   slot=lambda meter='choose':
                                                   self.mainProg.open_raw_data('chooseloop'),
                                                   enabled=False)
        self.mnFileAppendWorkspace = self.create_action("Append workspace...",
                                                        slot=self.mainProg.append_workspace,
                                                        enabled=False)
        self.mnFileClearWorkspace = self.create_action("Clear workspace",
                                                       slot=self.mainProg.workspace_clear,
                                                       enabled=True)
        self.mnFileSaveWorkspace = self.create_action("Save workspace...",
                                                      slot=self.mainProg.workspace_save,
                                                      enabled=False)
        self.mnFileLoadWorkspaceAction = self.create_action("Load workspace...",
                                                            slot=self.mainProg.workspace_load)
        self.mnFileExitAction = self.create_action("&Exit", slot=self.mainProg.close_windows, tip="Exit App")

        # add actions to menu
        self.add_actions(self.mnFile, (self.mnFileOpenScintrexFile,
                                       self.mnFileOpenCG6File,
                                       self.mnFileOpenBurrisFile,
                                       None,
                                       self.mnFileAppendSurvey,
                                       self.mnFileAppendLoop,
                                       self.mnFileAppendWorkspace,
                                       None,
                                       self.mnFileClearWorkspace,
                                       self.mnFileSaveWorkspace,
                                       self.mnFileLoadWorkspaceAction,
                                       None,
                                       self.mnFileExitAction))

        #######################################################################
        # Process Menu:
        #######################################################################
        self.mnEdit = self.mainProg.menuBar().addMenu("&Edit")
        self.mnEditTideCorrection = self.create_action("&Tide correction",
                                                       shortcut="Ctrl+T", slot=self.mainProg.tide_correction_dialog,
                                                       tip="Choose tide correction method", enabled=False)
        # for ocean loading correction
        self.oceanLoadingCorrectionAction = self.create_action("&Ocean loading correction",
                                                               shortcut="Ctrl+L", slot=self.mainProg.correction_ocean_loading,
                                                               tip="Ocean loading corrections", enabled=False)
        # for atmospheric correction
        self.atmosphericCorrectionAction = self.create_action("&Atmospheric correction",
                                                              shortcut="Ctrl+P", slot=self.mainProg.correction_atmospheric,
                                                              tip="Apply atmospheric correction by loading a data file",
                                                              enabled=False)
        self.mnEditComputeGravityChangeAction = self.create_action("&Compute gravity change",
                                                                   slot=self.mainProg.compute_gravity_change,
                                                                   tip="Compute gravity change", enabled=False)
        # for correcting time
        self.mnEditCorrectRecordedTimeAction = self.create_action("&Correct recorded time",
                                                                  slot=self.mainProg.correction_recorded_time,
                                                                  tip="Correct recorded time", enabled=False)
        self.mnEditVerticalGradientIntervalAction = self.create_action("&Vertical gradient interval...",
                                                                       slot=self.mainProg.set_vertical_gradient_interval,
                                                                       enabled=True)
        self.mnEditVerticalGradientWriteAction = self.create_action("Write vertical gradient file...",
                                                                    slot=self.mainProg.vertical_gradient_write,
                                                                    enabled=True)
        self.mnEditAddTareDialog = self.create_action("Add tare...",
                                                      slot=self.mainProg.add_tare,
                                                      enabled=True)
        self.mnEditLoops = self.create_action("Divide selected loop into subloops...",
                                              slot=self.mainProg.divide_survey,
                                              enabled=True)
        # add actions to menu
        self.add_actions(self.mnEdit,
                         (self.mnEditTideCorrection,
                          self.oceanLoadingCorrectionAction,
                          self.atmosphericCorrectionAction,
                          self.mnEditComputeGravityChangeAction,
                          self.mnEditCorrectRecordedTimeAction,
                          None,
                          self.mnEditLoops,
                          self.mnEditAddTareDialog,
                          None,
                          self.mnEditVerticalGradientIntervalAction,
                          self.mnEditVerticalGradientWriteAction))

        #######################################################################
        # Adjust Menu
        #######################################################################
        self.mnAdj = self.mainProg.menuBar().addMenu("&Adjustment")
        self.mnAdjtype = self.mnAdj.addMenu('Adjustment type')
        actiongroup_adjustmenttype = QtWidgets.QActionGroup(self.mainProg, exclusive=True)

        self.mnAdjPyLSQ = actiongroup_adjustmenttype.addAction(self.create_action('Numpy least squares', checkable=True))
        self.mnAdjtype.addAction(self.mnAdjPyLSQ)
        self.mnAdjGravnet = actiongroup_adjustmenttype.addAction(self.create_action('Gravnet', checkable=True))
        self.mnAdjtype.addAction(self.mnAdjGravnet)
        self.mnAdjGravnet.setChecked(True)

        self.mnAdjOptions = self.create_action("Adjust options...",
                                               slot=self.mainProg.show_adjust_options,
                                               enabled=True)
        self.mnAdjAdjust = self.create_action("&Adjust network",
                                              shortcut="Ctrl+1", slot=self.mainProg.adjust_network,
                                              tip="Least-square drift adjustment", enabled=False)
        self.mnAdjUpdateDeltas = self.create_action("&Populate delta table - all surveys",
                                                    shortcut="Ctrl+A",
                                                    slot=lambda: self.mainProg.populate_deltamodel('all'),
                                                    enabled=False)
        self.mnAdjUpdateDeltasCurrentSurvey = self.create_action("Populate delta table - selected survey",
                                                                 slot=lambda:
                                                                 self.mainProg.populate_deltamodel('selectedsurvey'),
                                                                 enabled=False)
        self.mnAdjUpdateDeltasCurrentLoop = self.create_action("Populate delta table - selected loop",
                                                               slot=lambda:
                                                               self.mainProg.populate_deltamodel('selectedloop'),
                                                               enabled=False)
        self.mnAdjClearDeltaTable = self.create_action("Clear delta table",
                                                       slot=self.mainProg.clear_delta_model,
                                                       enabled=False)
        self.mnAdjAdd = self.create_action("Add datum observation...",
                                           shortcut="Ctrl+D",
                                           slot=self.mainProg.add_datum_manually,
                                           enabled=True)
        self.mnAdjImportAbsSimple = self.create_action("Import abs. g (simple)...",
                                                       slot=self.mainProg.import_abs_g_simple,
                                                       enabled=True)
        self.mnAdjImportAbsFull = self.create_action("Import abs. g (complete)...",
                                                     slot=self.mainProg.import_abs_g_complete,
                                                     enabled=True)
        self.mnAdjImportAbsDatabase = self.create_action("Import abs. g from database...",
                                                         slot=self.mainProg.import_abs_g_direct,
                                                         enabled=True)
        self.mnAdjClearDatumTable = self.create_action("Clear datum table",
                                                       slot=self.mainProg.clear_datum_model,
                                                       enabled=False)

        self.mnAdjPlotHist = self.create_action("Plot residual histogram",
                                                shortcut="Ctrl+H", slot=self.mainProg.plot_adjust_residual_histogram,
                                                enabled=True)
        self.mnAdjCompareDatum = self.create_action("Plot adjusted datum vs. measured",
                                                    slot=self.mainProg.plot_compare_datum_to_adjusted,
                                                    enabled=True)
        # self.mnAdjCompareAllDatum = self.create_action("Plot absolute vs. relative offset",
        #                                                slot=self.mainProg.plot_compare_datum_all,
        #                                                enabled=True)

        self.add_actions(self.mnAdj, (self.mnAdjOptions,
                                      self.mnAdjAdjust,
                                      None,
                                      self.mnAdjUpdateDeltas,
                                      self.mnAdjUpdateDeltasCurrentSurvey,
                                      self.mnAdjUpdateDeltasCurrentLoop,
                                      self.mnAdjClearDeltaTable,
                                      None,
                                      self.mnAdjAdd,
                                      self.mnAdjImportAbsSimple,
                                      self.mnAdjImportAbsFull,
                                      self.mnAdjImportAbsDatabase,
                                      self.mnAdjClearDatumTable,
                                      None,
                                      self.mnAdjPlotHist,
                                      self.mnAdjCompareDatum))

        #######################################################################
        # Tools Menu
        #######################################################################
        self.mnTools = self.mainProg.menuBar().addMenu('&Tools')
        self.mnToolsNetworkGraphCircular = self.create_action('Network graph - circular',
                                                              slot=lambda map_type='circular':
                                                                  self.mainProg.plot_network_graph('circular'))
        self.mnToolsNetworkGraphMap = self.create_action('Network graph - map view',
                                                         slot=lambda map_type='map':
                                                         self.mainProg.plot_network_graph('map'))
        self.mnToolsWriteMetadataText = self.create_action('Write metadata text',
                                                           slot=self.mainProg.write_metadata_text)
        self.mnToolsWriteTabularOutput = self.create_action('Write tabular data',
                                                            slot=self.mainProg.write_tabular_data)
        self.add_actions(self.mnTools, (self.mnToolsNetworkGraphCircular,
                                        self.mnToolsNetworkGraphMap,
                                        None,
                                        self.mnToolsWriteMetadataText,
                                        self.mnToolsWriteTabularOutput))

        #######################################################################
        # Help Menu
        #######################################################################
        self.mnHelp = self.mainProg.menuBar().addMenu('&Help')
        self.mnHelpHelp = self.create_action('Help',
                                             slot=self.mainProg.show_help)
        self.mnHelpAbout = self.create_action('About',
                                              slot=about_dialog)
        self.add_actions(self.mnHelp, (self.mnHelpHelp,
                                       None,
                                       self.mnHelpAbout))

    def create_action(self, text, slot=None, shortcut=None, icon=None, tip=None, checkable=False,
                      signal="triggered()", enabled=True):
        """
        Simplify action creation
        """
        action = QtWidgets.QAction(text, self.mainProg)
        if icon is not None:
            action.setIcon(QtWidgets.QIcon(":/{}.png".format(icon)))
        if shortcut is not None:
            action.setShortcut(shortcut)
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        if checkable:
            action.setCheckable(True)
        if enabled is not True:
            action.setEnabled(False)
        return action

    def add_actions(self, target, actions):
        """
        Add actions to a target
        """
        for action in actions:
            if action is None:
                target.addSeparator()
            else:
                target.addAction(action)
