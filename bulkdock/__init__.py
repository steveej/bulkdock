#!/usr/bin/env python

import traceback, sys, copy
from yaml import load, dump
from string import Template
import argparse

def load_yml(filename):
    datafile = open(filename, "r")
    data = load(datafile)
    return data

def deepupdate(original, update):
    """
    Recursively update a dict.
    Subdict's won't be overwritten but also updated.
    """
    for key, value in original.iteritems(): 
        if not key in update:
            print("Debug: Writing missing key '%s'") % key
            update[key] = copy.deepcopy(value)
        elif isinstance(value, dict):
            deepupdate(value, update[key]) 
        else:
            print("Debug: Not overriding '%s'") % key
    return update

class YamlFilter:

    def __init__(self, data, gentoo_scheme):
        self._data = data
        self._gentoo_scheme = gentoo_scheme
        self._gentoo_data = None
        self._fig_data = None

    @property
    def fig_data(self):
        self._fig_data = copy.deepcopy(self._data)

        default = {}
        if "default" in self._fig_data:
            print("Debug: Found default section")
            default = copy.deepcopy(self._fig_data["default"])
            for def_key, def_value in self._fig_data["default"].iteritems():
                if def_key in self._gentoo_scheme["default"]:
                    del default[def_key]
            del self._fig_data["default"]

        for key, value in copy.deepcopy(self._fig_data).iteritems():
            for container_key, container_value in value.iteritems():
                if container_key in self._gentoo_scheme["default"]:
                    print("Debug: Deleting option %(1)s from container %(2)s") % {"1": container_key, "2": key}
                    del self._fig_data[key][container_key]
            self._fig_data[key] = deepupdate(copy.deepcopy(default), self._fig_data[key]) 
            if "build" not in self._fig_data[key] and "image" not in self._fig_data[key]:
                self._fig_data[key]["build"] = key

        return self._fig_data

    @property
    def gentoo_data(self):
        self._gentoo_data = copy.deepcopy(self._data)

        # find dicts with default values
        paths_to_default = []
        cur_path = []
        it = self._gentoo_data.iteritems()
        it_stack = [it]
        while(len(it_stack) > 0):
            tup = next(it_stack[-1], False)
            while(tup):
                depth = len(it_stack)-1
                if isinstance(tup[1], type(dict())):
                    it_stack.append(tup[1].iteritems())
                    cur_path.append(tup[0])
                    if tup[0] == "default":
                        print("Debug: Found default key in dictionary with depth %s and path %s") % (depth, cur_path)
                        paths_to_default.append(copy.deepcopy(cur_path))
                tup = next(it_stack[-1], False)
            it_stack.pop()

        # merge defaults from scheme and given data
        paths_to_default.sort(key=lambda el: len(el), reverse=False)
        for path in copy.deepcopy(paths_to_default):
            print("Debug: Processing path %s\n----------------------------") % path
            cur_data = self._gentoo_data
            cur_scheme = self._gentoo_scheme
            keyword = path.pop()
            assert(keyword == "default")
            for key in path:
                print("Debug: Recursing into %s") % key
                cur_data = cur_data[key]
                cur_scheme = cur_scheme[key]
            print("Debug: Current path is %s") % path

            overlap_keys = [overlap_key for overlap_key in set(cur_data["default"].keys())-set(cur_scheme["default"].keys())]
            if len(overlap_keys) > 0:
                print("Debug: overlapping keys not specified in scheme: %s. Deleting!") % overlap_keys
            for overlap_key in overlap_keys:
                del cur_data["default"][overlap_key]
            missing_keys = [missing_key for missing_key in set(cur_scheme["default"].keys())-set(cur_data["default"].keys())]
            if len(missing_keys) > 0:
                print("Debug: missing keys filled in from scheme: %s. Updating!") % missing_keys
                for missing_key in missing_keys:
                    cur_data["default"][missing_key] = copy.deepcopy(cur_scheme["default"][missing_key])
            print("Debug: Done with path %s\n----------------------------") % path


        # update every container with default values for every path
        defaults = copy.deepcopy(self._gentoo_data["default"])
        del self._gentoo_data["default"]
        paths_to_default.sort(key=lambda el: len(el), reverse=True)
        for container, values in self._gentoo_data.iteritems():
            deepupdate(defaults, values)
            for path in [path[1:] for path in paths_to_default if len(path) > 1]:
                print("Debug: Processing path %s\n----------------------------") % path
                cur_data = values
                keyword = path.pop()
                assert(keyword == "default")
                for key in path:
                    print("Debug: Recursing into %s") % key
                    cur_data = cur_data[key]
                print("Debug: Current path is %s") % path

                cur_default = copy.deepcopy(cur_data["default"])
                del cur_data["default"]
                for key, value in cur_data.iteritems():
                    print("Debug: Updating '%s' in '%s'") % (key, container)  
                    deepupdate(cur_default, value)
            
        print(dump(self._gentoo_data))

        return self._gentoo_data

import os
from jinja2 import ChoiceLoader, PrefixLoader, FileSystemLoader, Environment
class Generator():

    @staticmethod
    def render_gentoo_dockerfiles(gentoo_data, directory):
        for container, values in gentoo_data.iteritems():
            output_directory = "%s/%s" % (directory, container)
            out_file_path = "%s/Dockerfile" % (output_directory)

            # Load jinja templates from container or default path
            default_template_loader = FileSystemLoader("templates")
            jinja_loader = ChoiceLoader([
                    FileSystemLoader(container),
                    default_template_loader, 
                    PrefixLoader({"!templates": default_template_loader})
                ])
            jinja_env = Environment(loader=jinja_loader,
                                    trim_blocks=True,
                                    lstrip_blocks=True,
                                    extensions=["jinja2.ext.do"])
            # Get the template and render it 
            tmpl_file = jinja_env.get_template('Dockerfile.jinja')
            rendered_file = tmpl_file.render(**values)
            if not os.path.exists(output_directory):
                os.makedirs(output_directory)
            out_file = file(out_file_path, 'w')
            out_file.write(rendered_file)
            out_file.close()
            print("DEBUG: %s written." % out_file_path)


def main():

    PROJECT_YML_FILENAME="project.yml"
    SCHEME_YML_FILENAME="scheme.yml"

    parser = argparse.ArgumentParser()
    name_group = parser
    parser.add_argument('-n', '--name', default=None, help="Name of the project. Used for output file generations")
    parser.add_argument('-r', '--root', default=None, help="Path to the project's root directory")

    args = parser.parse_args()

    project_root = args.root
    project_name = args.name
    if project_name is None and project_root is None:
        project_root = os.path.abspath(os.curdir)
        print("DEBUG: Assuming %s as project root" % project_root)
        project_name = os.path.basename(project_root)
        print("DEBUG: Assuming %s as project name" % project_name)
    elif project_name is None:
        project_name = os.path.basename(os.path.abspath(project_root))
        print("DEBUG: Assuming %s as project name" % project_name)
    elif project_root is None:
        project_root = os.path.abspath(os.curdir)
        print("Assuming %s as project root" % project_root)

    output_directory = "%s/%s" % (project_root, "output")

    project_yml = load_yml("%s/%s" % (project_root, PROJECT_YML_FILENAME))
    scheme_yaml = load_yml("%s/%s" % (project_root, SCHEME_YML_FILENAME))
    yaml_filter = YamlFilter(project_yml, scheme_yaml)

    if not os.path.exists(output_directory):
        print("INFO: Creating %s" % output_directory)
        os.mkdir(output_directory)

    fig_yml = dump(yaml_filter.fig_data)
    fig_yml_file = open("%s/fig.yml" % (output_directory), "w")
    fig_yml_file.write(fig_yml)
    fig_yml_file.close()

    bulkdock_data = yaml_filter.gentoo_data
    bulkdock_yml = dump(bulkdock_data)
    bulkdock_yml_file = open("%s/bulkdock.yml" % (output_directory), "w")
    bulkdock_yml_file.write(bulkdock_yml)
    bulkdock_yml_file.close()

    Generator.render_gentoo_dockerfiles(bulkdock_data, output_directory)

if __name__ == "__main__":
    main()
