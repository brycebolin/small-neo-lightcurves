#!/bin/bash

# READ MY CSV HERE

# For i in row:
# sbatch ./my_python_executor.slurm $arg1 $arg2 $arg3 $arg4 $arg5

input="commands.txt"
while read -r line
do
	sbatch ./my_python_executor.slurm $line
done