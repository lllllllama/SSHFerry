import platform, sys, sysconfig
print("System:", platform.system(), platform.machine())
print("Platform tag:", sysconfig.get_platform())
print("Implementation:", sys.implementation.name)
