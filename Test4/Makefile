BINARY := './test'
ISSUE := 0
BEFORE := 5
AFTER := 5
RUN_TIME := 5
START_TIMESTAMP := 0
END_TIMESTAMP := 99999999999
ALL := 0

build:
	gcc ./test.c -gdwarf-2 -O0 -o $(BINARY) -lpthread

run: build
	readelf -s $(BINARY) | grep OBJECT | awk '{ print $$2,$$3,$$8 }' > $(BINARY).lst
	pin -t ../instrumenter/obj-intel64/racedet.so -s $(BINARY).lst -am $(ALL) -- $(BINARY)

graph: run
	../analyzer/analyzer.py -d ./
	../analyzer/grapher.py -d ./
	dot -T ps -o racedet.ps ./racedet.dot

report: run
	../analyzer/analyzer.py -d ./ -t $(RUN_TIME) -s $(START_TIMESTAMP) -e $(END_TIMESTAMP) -k knownissues.csv

explain:
	../analyzer/grapher.py -d ./ -j $(ISSUE) -b $(BEFORE) -a $(AFTER)
	dot -T ps -o racedet.ps ./racedet.dot

clean:
	-rm -rf $(BINARY) ./*.o ./*.*~ ./racedet* ./*.lst
