from pytools import memoize
# don't import pycuda.driver here--you'll create an import loop




@memoize
def get_nvcc_version(nvcc):
    from pytools.prefork import call_capture_stdout
    try:
        return call_capture_stdout([nvcc, "--version"])
    except OSError, e:
        raise OSError, "%s was not found (is it on the PATH?) [%s]" % (
                nvcc, str(e))




def _new_md5(): 
    try:
        import hashlib
        return hashlib.md5()
    except ImportError:
        # for Python << 2.5
        import md5
        return md5.new()




def compile_plain(source, options, keep, nvcc, cache_dir):
    from os.path import join

    if cache_dir:
        checksum = _new_md5()

        checksum.update(source)
        for option in options: 
            checksum.update(option)
        checksum.update(get_nvcc_version(nvcc))

        cache_file = checksum.hexdigest()
        cache_path = join(cache_dir, cache_file + ".cubin")

        try:
            return open(cache_path, "r").read()
        except:
            pass

    from tempfile import mkdtemp
    file_dir = mkdtemp()
    file_root = "kernel"

    cu_file_name = file_root + ".cu"
    cu_file_path = join(file_dir, cu_file_name)

    outf = open(cu_file_path, "w")
    outf.write(str(source))
    outf.close()

    if keep:
        options = options[:]
        options.append("--keep")

        print "*** compiler output in %s" % file_dir

    from pytools.prefork import call
    try:
        result = call([nvcc, "--cubin"]
                + options
                + [cu_file_name],
            cwd=file_dir)
    except OSError, e:
        raise OSError, "%s was not found (is it on the PATH?) [%s]" % (
                nvcc, str(e))

    if result != 0:
        from pycuda.driver import CompileError
        raise CompileError, "nvcc compilation of %s failed" % cu_file_path

    cubin = open(join(file_dir, file_root + ".cubin"), "r").read()

    if cache_dir:
        outf = open(cache_path, "w")
        outf.write(cubin)
        outf.close()

    if not keep:
        from os import listdir, unlink, rmdir
        for name in listdir(file_dir):
            unlink(join(file_dir, name))
        rmdir(file_dir)

    return cubin




def _get_per_user_string():
    try:
        from os import getuid
    except ImportError:
        checksum = _new_md5()
        from os import environ
        checksum.update(environ["HOME"])
        return checksum.hexdigest()
    else:
        return "uid%d" % getuid()




def _find_pycuda_include_path():
    from imp import find_module
    file, pathname, descr = find_module("pycuda")

    from os.path import join, exists
    installed_path = join(pathname, "..", "include", "pycuda")
    development_path = join(pathname, "..", "src", "cuda")
    development_path2 = join(pathname, "..", "..", "..", "src", "cuda")

    import sys
    usr_path = "/usr/include/pycuda"
    usr_local_path = "/usr/local/include/pycuda"
    prefix_path = join(sys.prefix, "include" , "pycuda")

    if exists(installed_path):
        return installed_path
    elif exists(development_path):
        return development_path
    elif exists(development_path2):
        return development_path2
    else:
        if sys.platform == "linux2":
            if exists(prefix_path):
                return prefix_path
            elif exists(usr_path):
                return usr_path
            elif exists(usr_local_path):
                return usr_local_path

        raise RuntimeError("could not find path to PyCUDA's C header files")



def compile(source, nvcc="nvcc", options=[], keep=False,
        no_extern_c=False, arch=None, code=None, cache_dir=None,
        include_dirs=[]):

    if not no_extern_c:
        source = 'extern "C" {\n%s\n}\n' % source

    options = options[:]
    if arch is None:
        try:
            from pycuda.driver import Context
            arch = "sm_%d%d" % Context.get_device().compute_capability()
        except RuntimeError:
            pass

    if cache_dir is None:
        from os.path import join
        from tempfile import gettempdir
        cache_dir = join(gettempdir(), 
                "pycuda-compiler-cache-v1-%s" % _get_per_user_string())

        from os import mkdir
        try:
            mkdir(cache_dir)
        except OSError, e:
            from errno import EEXIST
            if e.errno != EEXIST:
                raise

    if arch is not None:
        options.extend(["-arch", arch])

    if code is not None:
        options.extend(["-code", code])

    include_dirs = include_dirs + [_find_pycuda_include_path()]

    for i in include_dirs:
        options.append("-I"+i)

    return compile_plain(source, options, keep, nvcc, cache_dir)




class SourceModule(object):
    def __init__(self, source, nvcc="nvcc", options=[], keep=False,
            no_extern_c=False, arch=None, code=None, cache_dir=None,
            include_dirs=[]):
        cubin = compile(source, nvcc, options, keep, no_extern_c, 
                arch, code, cache_dir, include_dirs)

        from pycuda.driver import module_from_buffer
        self.module = module_from_buffer(cubin)

        self.get_global = self.module.get_global
        self.get_texref = self.module.get_texref

    def get_function(self, name):
        return self.module.get_function(name)
