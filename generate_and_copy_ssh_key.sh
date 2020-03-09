#!/usr/bin/env bash
# Modified version of: https://github.com/centic9/generate-and-send-ssh-key

# Defaults for the commandline-options
KEYSIZE=4096
PASSPHRASE=
FILENAME=~/.ssh/id_rsa
KEYTYPE=rsa

SSH_OPTS=""

while [[ $# > 0 ]]
do
	key="$1"
	shift
	case $key in
		-f*|--file)
			FILENAME="$1"
			shift
			;;
		-k*|--keysize)
			KEYSIZE="$1"
			shift
			;;
		-t*|--keytype)
			KEYTYPE="$1"
			shift
			;;
		-P*|--passphrase)
			PASSPHRASE="$1"
			shift
			;;
		*)
			# unknown option
			usage "unknown parameter: $key, "
			;;
	esac
done

# Ensure we have all necessary tools
SSH_KEYGEN=`which ssh-keygen`
SSH=`which ssh`

if [ -z "$SSH_KEYGEN" ]; then
    echo "Could not find the 'ssh-keygen' executable"
    exit 1
fi
if [ -z "$SSH" ]; then
    echo "Could not find the 'ssh' executable"
    exit 1
fi
echo

# Create SSH key (if necessary)
if [ ! -f $FILENAME ]; then
    echo "Generating a new ${KEYTYPE} SSH key @ ${FILENAME} with keysize ${KEYSIZE}"
    $SSH_KEYGEN -t $KEYTYPE -b $KEYSIZE  -f $FILENAME -N "$PASSPHRASE"
    RET=$?
    if [ $RET -ne 0 ]; then
        echo "ssh-keygen failed: ${RET}"
        exit 1
    fi
fi

# Copy SSH key to clipboard (running appropriate steps based on platform)
ENV="$(./determine_environment.sh)"
if [ "$ENV" = "Mac" ]; then
	pbcopy < "${FILENAME}.pub"
elif [ "$ENV" = "Linux" ]; then
	echo "Installing xclip..."
	sudo apt install -y xclip
	xclip -sel clip < "${FILENAME}.pub"
	echo ""
else
	echo "Could not copy key to clipboard, functionality not implemented for ${ENV} machines"
	exit 1
fi

echo "SSH key copied to clipboard"
