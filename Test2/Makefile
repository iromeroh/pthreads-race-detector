BINARY := './test'
ISSUE := 0
BEFORE := 5
AFTER := 5

build:
	gcc ./test.c -gdwarf-2 -O0 -o $(BINARY) -lpthread

run: build
	readelf -s $(BINARY) | grep OBJECT | awk '{ print $$2,$$3,$$8 }' > $(BINARY).lst
	pin -t ../instrumenter/obj-intel64/racedet.so -s $(BINARY).lst -- $(BINARY)

graph: run
	../analyzer/analyzer.py -d ./
	../analyzer/grapher.py -d ./
	dot -T ps -o racedet.ps ./racedet.dot

explain:
	../analyzer/grapher.py -d ./ -j $(ISSUE) -b $(BEFORE) -a $(AFTER)
	dot -T ps -o racedet.ps ./racedet.dot

clean:
	-rm -rf $(BINARY) ./*.o ./*.*~ ./racedet* ./*.lst
