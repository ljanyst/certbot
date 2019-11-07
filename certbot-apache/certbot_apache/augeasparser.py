"""
Augeas implementation of the ParserNode interfaces.

Augeas works internally by using XPATH notation. The following is a short example
of how this all works internally, to better understand what's going on under the
hood.

A configuration file /etc/apache2/apache2.conf with the following content:

    # First comment line
    # Second comment line
    WhateverDirective whatevervalue
    <ABlock>
        DirectiveInABlock dirvalue
    </ABlock>
    SomeDirective somedirectivevalue
    <ABlock>
        AnotherDirectiveInABlock dirvalue
    </ABlock>
    # Yet another comment


Translates over to Augeas path notation (of immediate children), when calling
for example: aug.match("/files/etc/apache2/apache2.conf/*")

[
    "/files/etc/apache2/apache2.conf/#comment[1]",
    "/files/etc/apache2/apache2.conf/#comment[2]",
    "/files/etc/apache2/apache2.conf/directive[1]",
    "/files/etc/apache2/apache2.conf/ABlock[1]",
    "/files/etc/apache2/apache2.conf/directive[2]",
    "/files/etc/apache2/apache2.conf/ABlock[2]",
    "/files/etc/apache2/apache2.conf/#comment[3]"
]

Regardless of directives name, its key in the Augeas tree is always "directive",
with index where needed of course. Comments work similarly, while blocks
have their own key in the Augeas XPATH notation.

It's important to note that all of the unique keys have their own indices.

Augeas paths are case sensitive, while Apache configuration is case insensitive.
It looks like this:

    <block>
        directive value
    </block>
    <Block>
        Directive Value
    </Block>
    <block>
        directive value
    </block>
    <bLoCk>
        DiReCtiVe VaLuE
    </bLoCk>

Translates over to:

[
    "/files/etc/apache2/apache2.conf/block[1]",
    "/files/etc/apache2/apache2.conf/Block[1]",
    "/files/etc/apache2/apache2.conf/block[2]",
    "/files/etc/apache2/apache2.conf/bLoCk[1]",
]
"""

from certbot_apache import apache_util
from certbot_apache import assertions
from certbot_apache import interfaces
from certbot_apache import parser
from certbot_apache import parsernode_util as util

from certbot.compat import os
from acme.magic_typing import Set  # pylint: disable=unused-import, no-name-in-module


class AugeasParserNode(interfaces.ParserNode):
    """ Augeas implementation of ParserNode interface """

    def __init__(self, **kwargs):
        ancestor, dirty, filepath, metadata = util.parsernode_kwargs(kwargs)  # pylint: disable=unused-variable
        super(AugeasParserNode, self).__init__(**kwargs)
        self.ancestor = ancestor
        self.filepath = filepath
        self.dirty = dirty
        self.metadata = metadata
        self.parser = self.metadata.get("augeasparser")

    def save(self, msg): # pragma: no cover
        pass


class AugeasCommentNode(AugeasParserNode):
    """ Augeas implementation of CommentNode interface """

    def __init__(self, **kwargs):
        comment, kwargs = util.commentnode_kwargs(kwargs)  # pylint: disable=unused-variable
        super(AugeasCommentNode, self).__init__(**kwargs)
        # self.comment = comment
        self.comment = comment

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self.comment == other.comment and
                    self.filepath == other.filepath and
                    self.dirty == other.dirty and
                    self.ancestor == other.ancestor and
                    self.metadata == other.metadata)
        return False


class AugeasDirectiveNode(AugeasParserNode):
    """ Augeas implementation of DirectiveNode interface """

    def __init__(self, **kwargs):
        name, parameters, enabled, kwargs = util.directivenode_kwargs(kwargs)
        super(AugeasDirectiveNode, self).__init__(**kwargs)
        self.name = name
        self.enabled = enabled
        if parameters:
            self.set_parameters(parameters)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self.name == other.name and
                    self.filepath == other.filepath and
                    self.parameters == other.parameters and
                    self.enabled == other.enabled and
                    self.dirty == other.dirty and
                    self.ancestor == other.ancestor and
                    self.metadata == other.metadata)
        return False

    def set_parameters(self, parameters):
        """
        Sets parameters of a DirectiveNode or BlockNode object.

        :param list parameters: List of all parameters for the node to set.
        """
        orig_params = self._aug_get_params(self.metadata["augeaspath"])

        # Clear out old parameters
        for _ in orig_params:
            # When the first parameter is removed, the indices get updated
            param_path = "{}/arg[1]".format(self.metadata["augeaspath"])
            self.parser.aug.remove(param_path)
        # Insert new ones
        for pi, param in enumerate(parameters):
            param_path = "{}/arg[{}]".format(self.metadata["augeaspath"], pi+1)
            self.parser.aug.set(param_path, param)

    @property
    def parameters(self):
        """
        Fetches the parameters from Augeas tree, ensuring that the sequence always
        represents the current state

        :returns: Tuple of parameters for this DirectiveNode
        :rtype: tuple:
        """
        return tuple(self._aug_get_params(self.metadata["augeaspath"]))

    def _aug_get_params(self, path):
        """Helper function to get parameters for DirectiveNodes and BlockNodes"""

        arg_paths = self.parser.aug.match(path + "/arg")
        return [self.parser.get_arg(apath) for apath in arg_paths]


class AugeasBlockNode(AugeasDirectiveNode):
    """ Augeas implementation of BlockNode interface """

    def __init__(self, **kwargs):
        super(AugeasBlockNode, self).__init__(**kwargs)
        self.children = ()

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return (self.name == other.name and
                    self.filepath == other.filepath and
                    self.parameters == other.parameters and
                    self.children == other.children and
                    self.enabled == other.enabled and
                    self.dirty == other.dirty and
                    self.ancestor == other.ancestor and
                    self.metadata == other.metadata)
        return False

    # pylint: disable=unused-argument
    def add_child_block(self, name, parameters=None, position=None):  # pragma: no cover
        """Adds a new BlockNode to the sequence of children"""

        insertpath, realpath, before = self._aug_resolve_child_position(
            name,
            position
        )
        new_metadata = {"augeasparser": self.parser, "augeaspath": realpath}

        # Create the new block
        self.parser.aug.insert(insertpath, name, before)

        # Parameters will be set at the initialization of the new object
        new_block = AugeasBlockNode(name=name,
                                    parameters=parameters,
                                    ancestor=assertions.PASS,
                                    filepath=apache_util.get_file_path(realpath),
                                    metadata=new_metadata)
        return new_block

    # pylint: disable=unused-argument
    def add_child_directive(self, name, parameters=None, position=None):  # pragma: no cover
        """Adds a new DirectiveNode to the sequence of children"""
        new_metadata = {"augeasparser": self.parser, "augeaspath": assertions.PASS}
        new_dir = AugeasDirectiveNode(name=assertions.PASS,
                                      ancestor=self,
                                      filepath=assertions.PASS,
                                      metadata=new_metadata)
        self.children += (new_dir,)
        return new_dir

    def add_child_comment(self, comment="", position=None):  # pylint: disable=unused-argument
        """Adds a new CommentNode to the sequence of children"""
        new_metadata = {"augeasparser": self.parser, "augeaspath": assertions.PASS}
        new_comment = AugeasCommentNode(comment=assertions.PASS,
                                        ancestor=self,
                                        filepath=assertions.PASS,
                                        metadata=new_metadata)
        self.children += (new_comment,)
        return new_comment

    def find_blocks(self, name, exclude=True): # pylint: disable=unused-argument
        """Recursive search of BlockNodes from the sequence of children"""

        nodes = list()
        paths = self._aug_find_blocks(name)
        if exclude:
            paths = self.parser.exclude_dirs(paths)
        for path in paths:
            nodes.append(self._create_blocknode(path))

        return nodes

    def find_directives(self, name, exclude=True): # pylint: disable=unused-argument
        """Recursive search of DirectiveNodes from the sequence of children"""

        nodes = list()
        ownpath = self.metadata.get("augeaspath")

        directives = self.parser.find_dir(name, start=ownpath, exclude=exclude)
        already_parsed = set()  # type: Set[str]
        for directive in directives:
            # Remove the /arg part from the Augeas path
            directive = directive.partition("/arg")[0]
            # find_dir returns an object for each _parameter_ of a directive
            # so we need to filter out duplicates.
            if directive not in already_parsed:
                nodes.append(self._create_directivenode(directive))
                already_parsed.add(directive)

        return nodes

    def find_comments(self, comment):
        """
        Recursive search of DirectiveNodes from the sequence of children.

        :param str comment: Comment content to search for.
        """

        nodes = list()
        ownpath = self.metadata.get("augeaspath")

        comments = self.parser.find_comments(comment, start=ownpath)
        for com in comments:
            nodes.append(self._create_commentnode(com))

        return nodes

    def delete_child(self, child):  # pragma: no cover
        """Deletes a ParserNode from the sequence of children"""
        pass

    def unsaved_files(self):  # pragma: no cover
        """Returns a list of unsaved filepaths"""
        return [assertions.PASS]

    def _create_commentnode(self, path):
        """Helper function to create a CommentNode from Augeas path"""

        comment = self.parser.aug.get(path)
        metadata = {"augeasparser": self.parser, "augeaspath": path}

        # Because of the dynamic nature of AugeasParser and the fact that we're
        # not populating the complete node tree, the ancestor has a dummy value
        return AugeasCommentNode(comment=comment,
                                 ancestor=assertions.PASS,
                                 filepath=apache_util.get_file_path(path),
                                 metadata=metadata)

    def _create_directivenode(self, path):
        """Helper function to create a DirectiveNode from Augeas path"""

        name = self.parser.get_arg(path)
        metadata = {"augeasparser": self.parser, "augeaspath": path}

        # Because of the dynamic nature, and the fact that we're not populating
        # the complete ParserNode tree, we use the search parent as ancestor
        return AugeasDirectiveNode(name=name,
                                   ancestor=assertions.PASS,
                                   filepath=apache_util.get_file_path(path),
                                   metadata=metadata)

    def _create_blocknode(self, path):
        """Helper function to create a BlockNode from Augeas path"""

        name = self._aug_get_name(path)
        metadata = {"augeasparser": self.parser, "augeaspath": path}

        # Because of the dynamic nature, and the fact that we're not populating
        # the complete ParserNode tree, we use the search parent as ancestor
        return AugeasBlockNode(name=name,
                               ancestor=assertions.PASS,
                               filepath=apache_util.get_file_path(path),
                               metadata=metadata)

    def _aug_find_blocks(self, name):
        """Helper function to perform a search to Augeas DOM tree to search
        configuration blocks with a given name"""

        # The code here is modified from configurator.get_virtual_hosts()
        blk_paths = set()
        for vhost_path in list(self.parser.parser_paths):
            paths = self.parser.aug.match(
                ("/files%s//*[label()=~regexp('%s')]" %
                    (vhost_path, parser.case_i(name))))
            blk_paths.update([path for path in paths if
                              name.lower() in os.path.basename(path).lower()])
        return blk_paths

    def _aug_get_name(self, path):
        """
        Helper function to get name of a configuration block or variable from path.
        """

        # Remove the ending slash if any
        if path[-1] == "/":  # pragma: no cover
            path = path[:-1]

        # Get the block name
        name = path.split("/")[-1]

        # remove [...], it's not allowed in Apache configuration and is used
        # for indexing within Augeas
        name = name.split("[")[0]
        return name

    def _aug_resolve_child_position(self, name, position):
        """
        Helper function that iterates through the immediate children and figures
        out the insertion path for a new AugeasParserNode.

        Augeas also generalizes indices for directives and comments, simply by
        using "directive" or "comment" respectively as their names.

        This function iterates over the existing children of the AugeasBlockNode,
        returning their insertion path, resulting Augeas path and if the new node
        should be inserted before or after the returned insertion path.

        Note: while Apache is case insensitive, Augeas is not, and blocks like
        Nameofablock and NameOfABlock have different indices.

        :param str name: Name of the AugeasBlockNode to insert, "directive" for
            AugeasDirectiveNode or "comment" for AugeasCommentNode
        :param int position: The position to insert the child AugeasParserNode to

        :returns: Tuple of insert path, resulting path and a boolean if the new
            node should be inserted before it.
        :rtype: tuple of str, str, bool
        """

        # Default to appending
        before = False

        all_children = self.parser.aug.match("{}/*".format(
            self.metadata["augeaspath"])
        )

        # Calculate resulting_path
        # Augeas indices start at 1. We use counter to calculate the index to
        # be used in resulting_path.
        counter = 1
        for i, child in enumerate(all_children):
            if position is not None and i >= position:
                # We're not going to insert the new node to an index after this
                break
            childname = self._aug_get_name(child)
            if name == childname:
                counter += 1

        resulting_path = "{}/{}[{}]".format(
            self.metadata["augeaspath"],
            name,
            counter
        )

        # Form the correct insert_path
        # Inserting the only child and appending as the last child work
        # similarly in Augeas.
        append = not all_children or position is None or position >= len(all_children)
        if append:
            insert_path = "{}/*[last()]".format(
                self.metadata["augeaspath"]
            )
        elif position == 0:
            # Insert as the first child, before the current first one.
            insert_path = all_children[0]
            before = True
        else:
            insert_path = "{}/*[{}]".format(
                self.metadata["augeaspath"],
                position
            )

        return (insert_path, resulting_path, before)


interfaces.CommentNode.register(AugeasCommentNode)
interfaces.DirectiveNode.register(AugeasDirectiveNode)
interfaces.BlockNode.register(AugeasBlockNode)