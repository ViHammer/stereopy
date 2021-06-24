#!/usr/bin/env python3
# coding: utf-8
"""
@author: Ping Qiu  qiuping1@genomics.cn
@last modified by: Ping Qiu
@file:stereo_exp_data.py
@time:2021/03/22
"""
from .data import Data
import pandas as pd
import numpy as np
from typing import Optional, Union
from scipy.sparse import spmatrix, csr_matrix
from shapely.geometry import Point, MultiPoint
import h5py
from ..io import h5ad
from functools import singledispatch


class StereoExpData(Data):
    def __init__(
            self,
            file_path: Optional[str] = None,
            file_format: Optional[str] = None,
            bin_type: Optional[str] = None,
            exp_matrix: Optional[Union[np.ndarray, spmatrix]] = None,
            genes: Optional[pd.DataFrame] = None,
            cells: Optional[pd.DataFrame] = None,
            position: Optional[np.ndarray] = None,
            output: Optional[str] = None,
            partitions: int = 1):
        super(StereoExpData, self).__init__(file_path=file_path, file_format=file_format,
                                            partitions=partitions, output=output)
        self._exp_matrix = exp_matrix
        self._genes = genes
        self._cells = cells
        self._position = position
        self._bin_type = bin_type

    def check(self):
        """
        checking whether the params is in the range.

        :return:
        """
        super(StereoExpData, self).check()
        self.bin_type_check(self._bin_type)

    def bin_type_check(self, bin_type):
        """
        check whether the bin type is in range.

        :param bin_type: bin type value, 'bins' or 'cell_bins'.
        :return:
        """
        if (bin_type is not None) and (bin_type not in ['bins', 'cell_bins']):
            self.logger.error(f"the bin type `{bin_type}` is not in the range, please check!")
            raise Exception

    @property
    def genes(self):
        """
        get the value of self._genes.

        :return:
        """
        return self._genes

    @genes.setter
    def genes(self, df):
        """
        set the value of self._genes.

        :param df:
        :return:
        """
        self._genes = df

    @property
    def cells(self):
        """
        get the value of self._cells

        :return:
        """
        return self._cells

    @cells.setter
    def cells(self, df):
        """
        set the value of self._cells.

        :param df: a dataframe whose index is cell id
        :return:
        """
        self._cells = df

    @property
    def exp_matrix(self):
        """
        get the value of self._exp_matrix.

        :return:
        """
        return self._exp_matrix

    @exp_matrix.setter
    def exp_matrix(self, pos_array):
        """
        set the value of self._exp_matrix.

        :param pos_array: np.ndarray or sparse.spmatrix.
        :return:
        """
        self._exp_matrix = pos_array

    @property
    def bin_type(self):
        """
        get the value of self._bin_type.

        :return:
        """
        return self._bin_type

    @bin_type.setter
    def bin_type(self, b_type):
        """
        set the value of self._bin_type.

        :param b_type: the value of bin type, 'bins' or 'cell_bins'.
        :return:
        """
        self.bin_type_check(b_type)
        self._bin_type = b_type

    @property
    def position(self):
        """
        get the value of self._position.

        :return:
        """
        return self._position

    @position.setter
    def position(self, pos):
        """
        set the value of self._position.

        :param pos: the value of position, a np.ndarray .
        :return:
        """
        self._position = pos

    def read_txt(self, sep='\t', bin_size=100, is_sparse=True):
        """
        read the stereo-seq file, and generate the object of StereoExpData.

        :param sep: separator string
        :param bin_size: the size of bin to merge. The parameter only takes effect
                         when the value of self.bin_type is 'bins'.
        :param is_sparse: the matrix is sparse matrix if is_sparse is True else np.ndarray

        :return: an object of StereoExpData.
        """
        df = pd.read_csv(str(self.file), sep=sep, comment='#', header=0)
        df.dropna(inplace=True)
        gdf = None
        if self.bin_type == 'cell_bins':
            df.rename(columns={'label': 'cell_id'}, inplace=True)
            gdf = self.parse_cell_bin_coor(df)
        else:
            df = self.parse_bin_coor(df, bin_size)
        cells = df['cell_id'].unique()
        genes = df['geneID'].unique()
        cells_dict = dict(zip(cells, range(0, len(cells))))
        genes_dict = dict(zip(genes, range(0, len(genes))))
        rows = df['cell_id'].map(cells_dict)
        cols = df['geneID'].map(genes_dict)
        self.logger.info(f'the martrix has {len(cells)} cells, and {len(genes)} genes.')
        exp_matrix = csr_matrix((df['UMICount'], (rows, cols)), shape=(cells.shape[0], genes.shape[0]), dtype=np.int)
        self.cells = pd.DataFrame(index=cells)
        self.genes = pd.DataFrame(index=genes)
        self.exp_matrix = exp_matrix if is_sparse else exp_matrix.toarray()
        if self.bin_type == 'bins':
            self.position = df.loc[:, ['x_center', 'y_center']].drop_duplicates().values
        else:
            self.position = gdf.loc[cells][['x_center', 'y_center']].values
            self.cells['cell_point'] = gdf.loc[cells]['cell_point']
        return self

    def parse_bin_coor(self, df, bin_size):
        """
        merge bins to a bin unit according to the bin size, also calculate the center coordinate of bin unit,
        and generate cell id of bin unit using the coordinate after merged.

        :param df: a dataframe of the bin file.
        :param bin_size: the size of bin to merge.
        :return:
        """
        x_min = df['x'].min()
        y_min = df['y'].min()
        df['bin_x'] = self.merge_bin_coor(df['x'].values, x_min, bin_size)
        df['bin_y'] = self.merge_bin_coor(df['y'].values, y_min, bin_size)
        df['cell_id'] = df['bin_x'].astype(str) + '_' + df['bin_y'].astype(str)
        df['x_center'] = self.get_bin_center(df['bin_x'], x_min, bin_size)
        df['y_center'] = self.get_bin_center(df['bin_y'], y_min, bin_size)
        return df

    def parse_cell_bin_coor(self, df):
        gdf = df.groupby('cell_id').apply(lambda x: self.make_multipoint(x))
        return gdf

    @staticmethod
    def make_multipoint(x):
        p = [Point(i) for i in zip(x['x'], x['y'])]
        mlp = MultiPoint(p).convex_hull
        x_center = mlp.centroid.x
        y_center = mlp.centroid.y
        return pd.Series({'cell_point': mlp, 'x_center': x_center, 'y_center': y_center})

    @staticmethod
    def merge_bin_coor(coor: np.ndarray, coor_min: int, bin_size: int):
        return np.floor((coor-coor_min)/bin_size).astype(np.int)

    @staticmethod
    def get_bin_center(bin_coor: np.ndarray, coor_min: int, bin_size: int):
        return bin_coor*bin_size+coor_min+int(bin_size/2)

    def read_h5ad(self):
        """
        read the h5ad file, and generate the object of StereoExpData.
        :return:
        """
        if not self.file.exists():
            self.logger.error('the input file is not exists, please check!')
            raise FileExistsError('the input file is not exists, please check!')
        with h5py.File(self.file, mode='r') as f:
            for k in f.keys():
                if k == 'cells':
                    self.cells = h5ad.read_group(f[k])
                elif k == 'genes':
                    self.genes = h5ad.read_group(f[k])
                elif k == 'position':
                    self.position = h5ad.read_dataset(f[k])
                elif k == 'bin_type':
                    self.bin_type = h5ad.read_dataset(f[k])
                elif k == 'exp_matrix':
                    if isinstance(f[k], h5py.Group):
                        self.exp_matrix = h5ad.read_group(f[k])
                    else:
                        self.exp_matrix = h5ad.read_dataset(f[k])
                else:
                    pass
        return self

    def read(self, sep='\t', bin_size=100, is_sparse=True):
        """
        read different format file and generate the object of StereoExpData.

        :param sep: separator string
        :param bin_size: the size of bin to merge. The parameter only takes effect
                         when the value of self.bin_type is 'bins'.
        :param is_sparse: the matrix is sparse matrix if is_sparse is True else np.ndarray
        :return:
        """
        if self.file_format == 'txt':
            return self.read_txt(sep=sep, bin_size=bin_size, is_sparse=is_sparse)
        elif self.file_format == 'h5ad':
            return self.read_h5ad()
        else:
            pass

    def write_h5ad(self):
        """
        write the SetreoExpData into h5ad file.
        :return:
        """
        if self.output is None:
            self.logger.error("the output path must be set before writting.")
        with h5py.File(self.output, mode='w') as f:
            h5ad.write(self.genes, f, 'genes')
            h5ad.write(self.cells, f, 'cells')
            h5ad.write(self.position, f, 'position')
            sp_format = 'csr' if isinstance(self.exp_matrix, csr_matrix) else 'csc'
            h5ad.write(self.exp_matrix, f, 'exp_matrix', sp_format)
            h5ad.write(self.bin_type, f, 'bin_type')

    def write(self):
        """
        write the SetreoExpData into file.

        :return:
        """
        self.write_h5ad()

    def read_by_bulk(self):
        pass
