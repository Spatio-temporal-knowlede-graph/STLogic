import os
import json
import numpy as np


class Grapher(object):
    def __init__(self, dataset_dir):
        """
        Store information about the graph (train/valid/test set).
        Add corresponding inverse quadruples to the data.

        Parameters:
            dataset_dir (str): path to the graph dataset directory

        Returns:
            None
        """

        self.dataset_dir = dataset_dir
        self.entity2id = json.load(open(dataset_dir + "entity2id.json", encoding="utf-8"))
        self.relation2id_old = json.load(open(dataset_dir + "relation2id.json", encoding="utf-8"))
        self.relation2id = self.relation2id_old.copy()
        counter = len(self.relation2id_old)
        for relation in self.relation2id_old:
            self.relation2id["_" + relation] = counter  # Inverse relation
            counter += 1
        self.ts2id = json.load(open(dataset_dir + "ts2id.json", encoding="utf-8"))
        self.id2entity = dict([(v, k) for k, v in self.entity2id.items()])
        self.id2relation = dict([(v, k) for k, v in self.relation2id.items()])
        self.id2ts = dict([(v, k) for k, v in self.ts2id.items()])

        self.inv_relation_id = dict()
        num_relations = len(self.relation2id_old)
        for i in range(num_relations):
            self.inv_relation_id[i] = i + num_relations
        for i in range(num_relations, num_relations * 2):
            self.inv_relation_id[i] = i % num_relations

        # STLogic: per-row head location "easting,northing" (5th column), keyed by
        # (subject_id, ts_id). Empty for datasets without the extra column (e.g. ICEWS).
        self.loc_by_sub_ts = {}
        self.train_idx = self.create_store("train.txt")
        self.valid_idx = self.create_store("valid.txt")
        self.test_idx = self.create_store("test.txt")
        self.all_idx = np.vstack((self.train_idx, self.valid_idx, self.test_idx))

        # STLogic: static landmark coordinates from landmarks.tsv (optional file).
        self.landmark_pos = self.load_landmarks()
        # STLogic: entity type (for type-conditioned spatial models), optional file.
        self.entity_type = self.load_entity_types()

        print("Grapher initialized.")

    def load_entity_types(self):
        """Load entity_types.tsv (entity \\t type) if present -> {entity_id: type}."""
        entity_type = {}
        path = self.dataset_dir + "entity_types.tsv"
        if not os.path.exists(path):
            return entity_type
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 2 and parts[0] in self.entity2id:
                    entity_type[self.entity2id[parts[0]]] = parts[1]
        return entity_type

    def load_landmarks(self):
        """Load landmarks.tsv (entity \\t easting \\t northing) if present."""
        landmark_pos = {}
        path = self.dataset_dir + "landmarks.tsv"
        if not os.path.exists(path):
            return landmark_pos
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 3 and parts[0] in self.entity2id:
                    landmark_pos[self.entity2id[parts[0]]] = (
                        float(parts[1]),
                        float(parts[2]),
                    )
        return landmark_pos

    def create_store(self, file):
        """
        Store the quadruples from the file as indices.
        The quadruples in the file should be in the format "subject\trelation\tobject\ttimestamp\n".

        Parameters:
            file (str): file name

        Returns:
            store_idx (np.ndarray): indices of quadruples
        """

        with open(self.dataset_dir + file, "r", encoding="utf-8") as f:
            quads = f.readlines()
        store = self.split_quads(quads)
        store_idx = self.map_to_idx(store)
        store_idx = self.add_inverses(store_idx)

        return store_idx

    def split_quads(self, quads):
        """
        Split quadruples into a list of strings.

        Parameters:
            quads (list): list of quadruples
                          Each quadruple has the form "subject\trelation\tobject\ttimestamp\n".

        Returns:
            split_q (list): list of quadruples
                            Each quadruple has the form [subject, relation, object, timestamp].
        """

        split_q = []
        for quad in quads:
            split_q.append(quad[:-1].split("\t"))

        return split_q

    def map_to_idx(self, quads):
        """
        Map quadruples to their indices.

        Parameters:
            quads (list): list of quadruples
                          Each quadruple has the form [subject, relation, object, timestamp].

        Returns:
            quads (np.ndarray): indices of quadruples
        """

        subs = [self.entity2id[x[0]] for x in quads]
        rels = [self.relation2id[x[1]] for x in quads]
        objs = [self.entity2id[x[2]] for x in quads]
        tss = [self.ts2id[x[3]] for x in quads]

        # STLogic: capture the optional 5th column (head location "easting,northing")
        # into loc_by_sub_ts[(subject_id, ts_id)]. Silently ignored when absent.
        for x in quads:
            if len(x) > 4 and x[4]:
                try:
                    e_str, n_str = x[4].split(",")
                    self.loc_by_sub_ts[(self.entity2id[x[0]], self.ts2id[x[3]])] = (
                        float(e_str),
                        float(n_str),
                    )
                except (ValueError, KeyError):
                    pass

        quads = np.column_stack((subs, rels, objs, tss))

        return quads

    def add_inverses(self, quads_idx):
        """
        Add the inverses of the quadruples as indices.

        Parameters:
            quads_idx (np.ndarray): indices of quadruples

        Returns:
            quads_idx (np.ndarray): indices of quadruples along with the indices of their inverses
        """

        subs = quads_idx[:, 2]
        rels = [self.inv_relation_id[x] for x in quads_idx[:, 1]]
        objs = quads_idx[:, 0]
        tss = quads_idx[:, 3]
        inv_quads_idx = np.column_stack((subs, rels, objs, tss))
        quads_idx = np.vstack((quads_idx, inv_quads_idx))

        return quads_idx
