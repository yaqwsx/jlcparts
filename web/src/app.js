import React from 'react';

import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@fortawesome/free-solid-svg-icons'
import { far } from '@fortawesome/free-regular-svg-icons'
import { fab } from '@fortawesome/free-brands-svg-icons'

import './main.css';
import { updateComponentLibrary, checkForComponentLibraryUpdate, db } from './db'
import { ComponentOverview } from './componentTable'

library.add(fas, far, fab);

function Header(props) {
  return <div className="w-full px-2 py-8 flex">
    <img src="./favicon.svg" alt="" className="block flex-none mr-4 h-auto"/>
    <div className="flex-1">
      <h1 className="text-4xl font-bold">
        JLC PCB SMD Assembly Component Catalogue
      </h1>
      <p>
        Parametric search for components offered by <a href="https://jlcpcb.com">JLC PCB</a> SMD assembly service.
      </p>
      <p>
        Read more at project's <a className="underline text-blue-500 hover:text-blue-800" href="https://github.com/yaqwsx/jlcparts">GitHub page</a>.
      </p>
    </div>
  </div>
}

function Footer(props) {
  return <div className="w-full p-2 border-t-2 border-gray-800" style={{"minHeight": "200px"}}>

  </div>
}

class FirstTimeNote extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      "componentCount": undefined
    };
  }

  componentDidMount() {
    db.components.count().then(x => {
      this.setState({"componentCount": x});
    })
  }

  render() {
    if (this.state.componentCount === undefined || this.state.componentCount !== 0)
      return <></>
    return <div className="w-full p-8 my-2 bg-yellow-400 rounded">
      <p>
        Hey, it seems that you run the application for the first time, hence,
        there's no component library in your device. Just press the "Update
        the component library button" in the upper right corner to download it
        and use the app.
      </p>
      <p>
        Note that the initial download of the component library might take a while.
      </p>
    </div>
  }
}

class UpdateBar extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      "updateAvailable": this.props.updateAvailable
    };
  }

  componentDidMount() {
    let checkStatus = () => {
      checkForComponentLibraryUpdate().then( updateAvailable => {
        this.setState({"updateAvailable": updateAvailable});
      });
      db.settings.get("lastUpdate").then(x => {
        this.setState({"lastUpdate": x});
      })
    };

    checkStatus();
    this.timerID = setInterval(checkStatus, 60000);
  }

  componentWillUnmount() {
    clearInterval(this.timerID);
  }

  handleUpdateClick = (e) => {
    e.preventDefault();
    this.props.onTriggerUpdate();
  }

  render() {
    if (this.state.updateAvailable) {
      return <div className="flex flex-wrap w-full align-middle bg-yellow-400 p-2">
                <p className="inline-block w-full md:w-1/2 py-2">There is an update of the component library available.</p>
                <button className="inline-block w-full md:w-1/2 bg-green-500 hover:bg-green-600 py-2 px-4 rounded"
                        onClick={this.handleUpdateClick}>
                  Update the component library
                </button>
              </div>
    }
    else {
    return <div className="w-full bg-green-400 p-2 text-xs">
              <p>The component database is up to-date {this.state.lastUpdate ? `(${this.state.lastUpdate})` : ""}.</p>
            </div>
    }
  }
}

class Updater extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      "progress": {}
    };
  }

  componentDidMount() {
    let t0 = performance.now();
    updateComponentLibrary(
      (progress) => { this.setState({"progress": progress}); }
    ).then(() => {
      let t1 = performance.now();
      console.log("Library update took ", t1 - t0, "ms");
      this.props.onFinish();
    });
  }

  listItems() {
    let items = []
    for (const [task, status] of Object.entries(this.state.progress)) {
      let color = status[1] ? "bg-green-500" : "bg-yellow-400";
      items.push(<tr key={task}>
        <td className="p-2">{task}</td>
        <td className={`p-2 ${color}`}>{status[0]}</td>
      </tr>)
    }
    return items;
  }

  render() {
    return <div className="w-full px-2 py-8">
      <h1 className="font-bold text-2xl">Update progress:</h1>
      <table className="w-full">
        <thead>
          <tr className="border-b-2 border-gray-800 font-bold">
            <td>Operation/category</td>
            <td>Progress</td>
          </tr>
        </thead>
        <tbody>
          {this.listItems()}
        </tbody>
      </table>
    </div>
  }
}

function Container(props) {
  return <div className="container mx-auto px-2">{props.children}</div>
}

class App extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      "updating": false
    };
  }

  onUpdateFinish = () => {
    this.setState({"updating": false});
  }

  triggerUpdate = () => {
    this.setState({"updating": true});
  }

  render() {
    if (this.state.updating) {
      return <Container>
        <Updater onFinish={this.onUpdateFinish}/>
      </Container>
    }
    return (
        <Container>
          <UpdateBar onTriggerUpdate={this.triggerUpdate}/>
          <Header/>
          <FirstTimeNote/>
          <ComponentOverview/>
          <Footer/>
        </Container>
    );
  }
}

export default App;