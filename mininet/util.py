"Utility functions for Mininet."

from time import sleep
from resource import setrlimit, RLIMIT_NPROC, RLIMIT_NOFILE
import select
from subprocess import call, check_call, Popen, PIPE, STDOUT

from mininet.log import lg

def run( cmd ):
    """Simple interface to subprocess.call()
       cmd: list of command params"""
    return call( cmd.split( ' ' ) )

def checkRun( cmd ):
    """Simple interface to subprocess.check_call()
       cmd: list of command params"""
    check_call( cmd.split( ' ' ) )

def quietRun( cmd ):
    """Run a command, routing stderr to stdout, and return the output.
       cmd: list of command params"""
    if isinstance( cmd, str ):
        cmd = cmd.split( ' ' )
    popen = Popen( cmd, stdout=PIPE, stderr=STDOUT )
    # We can't use Popen.communicate() because it uses
    # select(), which can't handle
    # high file descriptor numbers! poll() can, however.
    output = ''
    readable = select.poll()
    readable.register( popen.stdout )
    while True:
        while readable.poll():
            data = popen.stdout.read( 1024 )
            if len( data ) == 0:
                break
            output += data
        popen.poll()
        if popen.returncode != None:
            break
    return output

# Interface management
#
# Interfaces are managed as strings which are simply the
# interface names, of the form 'nodeN-ethM'.
#
# To connect nodes, we create a pair of veth interfaces, and then place them
# in the pair of nodes that we want to communicate. We then update the node's
# list of interfaces and connectivity map.
#
# For the kernel datapath, switch interfaces
# live in the root namespace and thus do not have to be
# explicitly moved.

def makeIntfPair( intf1, intf2 ):
    """Make a veth pair connecting intf1 and intf2.
       intf1: string, interface
       intf2: string, interface
       returns: success boolean"""
    # Delete any old interfaces with the same names
    quietRun( 'ip link del ' + intf1 )
    quietRun( 'ip link del ' + intf2 )
    # Create new pair
    cmd = 'ip link add name ' + intf1 + ' type veth peer name ' + intf2
    return checkRun( cmd )

def retry( retries, delaySecs, fn, *args, **keywords ):
    """Try something several times before giving up.
       n: number of times to retry
       delaySecs: wait this long between tries
       fn: function to call
       args: args to apply to function call"""
    tries = 0
    while not fn( *args, **keywords ) and tries < retries:
        sleep( delaySecs )
        tries += 1
    if tries >= retries:
        lg.error( "*** gave up after %i retries\n" % tries )
        exit( 1 )

def moveIntfNoRetry( intf, node, printError=False ):
    """Move interface to node, without retrying.
       intf: string, interface
       node: Node object
       printError: if true, print error"""
    cmd = 'ip link set ' + intf + ' netns ' + repr( node.pid )
    quietRun( cmd )
    links = node.cmd( 'ip link show' )
    if not intf in links:
        if printError:
            lg.error( '*** Error: moveIntf: ' + intf +
                ' not successfully moved to ' + node.name + '\n' )
        return False
    return True

def moveIntf( intf, node, printError=False, retries=3, delaySecs=0.001 ):
    """Move interface to node, retrying on failure.
       intf: string, interface
       node: Node object
       printError: if true, print error"""
    retry( retries, delaySecs, moveIntfNoRetry, intf, node, printError )

def createLink( node1, node2, retries=10, delaySecs=0.001 ):
    """Create a link between nodes, making an interface for each.
       node1: Node object
       node2: Node object"""
    intf1 = node1.newIntf()
    intf2 = node2.newIntf()
    makeIntfPair( intf1, intf2 )
    if node1.inNamespace:
        retry( retries, delaySecs, moveIntf, intf1, node1 )
    if node2.inNamespace:
        retry( retries, delaySecs, moveIntf, intf2, node2 )
    node1.connection[ intf1 ] = ( node2, intf2 )
    node2.connection[ intf2 ] = ( node1, intf1 )
    return intf1, intf2

def fixLimits():
    "Fix ridiculously small resource limits."
    setrlimit( RLIMIT_NPROC, ( 4096, 8192 ) )
    setrlimit( RLIMIT_NOFILE, ( 16384, 32768 ) )

def _colonHex( val, bytes ):
    """Generate colon-hex string.
       val: input as unsigned int
       bytes: number of bytes to convert
       returns: chStr colon-hex string"""
    pieces = []
    for i in range( bytes - 1, -1, -1 ):
        piece = ( ( 0xff << ( i * 8 ) ) & val ) >> ( i * 8 )
        pieces.append( '%02x' % piece )
    chStr = ':'.join( pieces )
    return chStr

def macColonHex( mac ):
    """Generate MAC colon-hex string from unsigned int.
       mac: MAC address as unsigned int
       returns: macStr MAC colon-hex string"""
    return _colonHex( mac, 6 )

def ipStr( ip ):
    """Generate IP address string
       returns: ip addr string"""
    hi = ( ip & 0xff0000 ) >> 16
    mid = ( ip & 0xff00 ) >> 8
    lo = ip & 0xff
    return "10.%i.%i.%i" % ( hi, mid, lo )